"""Núcleo do conversor: transforma arquivos RAW (.NEF) em JPEG ou PNG."""

from __future__ import annotations

import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import rawpy
from PIL import Image

log = logging.getLogger(__name__)

EXTENSOES_RAW = {".nef", ".nrw"}
FORMATOS = {"jpeg": ".jpg", "png": ".png"}

# Tags da imagem principal que descrevem a estrutura do arquivo RAW (tamanho,
# compressão, offsets...). Elas não fazem sentido no JPEG/PNG gerado.
_TAGS_ESTRUTURA = {
    256, 257, 258, 259, 262, 273, 277, 278, 279, 284, 317, 330, 338,
    513, 514, 530, 531, 700, 34665, 34853,
}
_TAG_ORIENTACAO = 274
_TAG_MAKERNOTE = 37500
_IFD_EXIF = 0x8769
_IFD_GPS = 0x8825


@dataclass
class Opcoes:
    """Parâmetros da conversão."""

    formato: str = "jpeg"           # "jpeg" ou "png"
    qualidade: int = 92             # 1-100, só para JPEG
    max_lado: int | None = None     # redimensiona o maior lado (px); None = original
    balanco_camera: bool = True     # usa o balanço de branco gravado pela câmera
    brilho_auto: bool = True        # ajuste automático de brilho do LibRaw
    manter_exif: bool = True        # copia data, câmera, lente, ISO etc.

    def __post_init__(self) -> None:
        self.formato = self.formato.lower()
        if self.formato == "jpg":
            self.formato = "jpeg"
        if self.formato not in FORMATOS:
            raise ValueError(f"Formato inválido: {self.formato!r} (use jpeg ou png)")
        if not 1 <= self.qualidade <= 100:
            raise ValueError("Qualidade deve estar entre 1 e 100")

    @property
    def extensao(self) -> str:
        return FORMATOS[self.formato]


@dataclass
class Resultado:
    origem: Path
    destino: Path | None
    status: str                     # "convertido", "pulado" ou "erro"
    mensagem: str = ""


@dataclass
class Resumo:
    saida: Path | None = None
    resultados: list[Resultado] = field(default_factory=list)

    def contar(self, status: str) -> int:
        return sum(1 for r in self.resultados if r.status == status)

    @property
    def erros(self) -> list[Resultado]:
        return [r for r in self.resultados if r.status == "erro"]


def encontrar_raws(pasta: Path, recursivo: bool = False,
                   ignorar: Path | None = None) -> list[Path]:
    """Lista os arquivos RAW da pasta (sem diferenciar maiúsculas/minúsculas)."""
    padrao = "**/*" if recursivo else "*"
    ignorar = ignorar.resolve() if ignorar else None
    arquivos = []
    for p in pasta.glob(padrao):
        if not (p.is_file() and p.suffix.lower() in EXTENSOES_RAW):
            continue
        if ignorar and ignorar in p.resolve().parents:
            continue
        arquivos.append(p)
    return sorted(arquivos)


def caminho_destino(arquivo: Path, entrada: Path, saida: Path, opcoes: Opcoes) -> Path:
    """Mantém a mesma estrutura de subpastas da entrada dentro da saída."""
    relativo = arquivo.relative_to(entrada)
    return (saida / relativo).with_suffix(opcoes.extensao)


def _exif_limpo(arquivo: Path) -> Image.Exif | None:
    """Lê o EXIF do NEF e remove o que não serve para o arquivo final.

    O NEF é baseado em TIFF, então o Pillow consegue ler suas tags. Removemos as
    tags de estrutura do RAW e o MakerNote (bloco proprietário da Nikon que pode
    passar do limite de 64 KB do EXIF em JPEG). A orientação vira 1 porque o
    LibRaw já entrega a imagem na rotação correta.
    """
    try:
        with Image.open(arquivo) as im:
            original = im.getexif()
            exif_ifd = dict(original.get_ifd(_IFD_EXIF))
            gps_ifd = dict(original.get_ifd(_IFD_GPS))
    except Exception as exc:  # EXIF é opcional: nunca impede a conversão
        log.debug("Sem EXIF em %s: %s", arquivo, exc)
        return None

    exif = Image.Exif()
    for tag, valor in original.items():
        if tag not in _TAGS_ESTRUTURA:
            exif[tag] = valor
    exif[_TAG_ORIENTACAO] = 1

    exif_ifd.pop(_TAG_MAKERNOTE, None)
    if exif_ifd:
        exif.get_ifd(_IFD_EXIF).update(exif_ifd)
    if gps_ifd:
        exif.get_ifd(_IFD_GPS).update(gps_ifd)
    return exif


def converter_arquivo(arquivo: Path, destino: Path, opcoes: Opcoes,
                      sobrescrever: bool = False) -> Resultado:
    """Converte um único arquivo RAW."""
    if destino.exists() and not sobrescrever:
        return Resultado(arquivo, destino, "pulado", "já existe")

    temporario = destino.with_name(destino.name + ".tmp")
    try:
        with rawpy.imread(str(arquivo)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=opcoes.balanco_camera,
                no_auto_bright=not opcoes.brilho_auto,
                output_bps=8,
            )
        imagem = Image.fromarray(rgb)

        if opcoes.max_lado and max(imagem.size) > opcoes.max_lado:
            imagem.thumbnail((opcoes.max_lado, opcoes.max_lado), Image.Resampling.LANCZOS)

        params: dict = {}
        if opcoes.manter_exif:
            exif = _exif_limpo(arquivo)
            if exif is not None:
                params["exif"] = exif
        if opcoes.formato == "jpeg":
            params.update(quality=opcoes.qualidade, optimize=True, subsampling=0)
        else:
            params.update(optimize=False, compress_level=6)

        destino.parent.mkdir(parents=True, exist_ok=True)
        imagem.save(temporario, format=opcoes.formato.upper(), **params)
        temporario.replace(destino)  # evita arquivos pela metade se algo falhar
        return Resultado(arquivo, destino, "convertido")
    except Exception as exc:
        temporario.unlink(missing_ok=True)
        return Resultado(arquivo, destino, "erro", f"{type(exc).__name__}: {exc}")


def _tarefa(args: tuple[Path, Path, Opcoes, bool]) -> Resultado:
    return converter_arquivo(*args)


def converter_pasta(
    entrada: Path,
    saida: Path | None = None,
    opcoes: Opcoes | None = None,
    recursivo: bool = False,
    sobrescrever: bool = False,
    processos: int | None = None,
    ao_progredir: Callable[[int, int, Resultado], None] | None = None,
) -> Resumo:
    """Converte todos os RAW de `entrada` e grava em `saida`.

    Se `saida` não for informada, cria a pasta "convertidos_<formato>" dentro
    da própria pasta de entrada.
    """
    entrada = Path(entrada).expanduser()
    if not entrada.is_dir():
        raise NotADirectoryError(f"Pasta não encontrada: {entrada}")
    opcoes = opcoes or Opcoes()
    saida = Path(saida).expanduser() if saida else entrada / f"convertidos_{opcoes.formato}"

    arquivos = encontrar_raws(entrada, recursivo, ignorar=saida)
    tarefas = [(a, caminho_destino(a, entrada, saida, opcoes), opcoes, sobrescrever)
               for a in arquivos]
    resumo = Resumo(saida=saida)
    total = len(tarefas)

    def registrar(resultado: Resultado) -> None:
        resumo.resultados.append(resultado)
        if ao_progredir:
            ao_progredir(len(resumo.resultados), total, resultado)

    if processos == 1 or total <= 1:
        for t in tarefas:
            registrar(_tarefa(t))
    else:
        # "spawn" evita travamentos do LibRaw/OpenMP com "fork" no Linux.
        contexto = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=processos, mp_context=contexto) as pool:
            for futuro in as_completed(pool.submit(_tarefa, t) for t in tarefas):
                registrar(futuro.result())

    resumo.resultados.sort(key=lambda r: r.origem)
    return resumo

