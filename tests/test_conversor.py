import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conversor_nef import Opcoes, converter_pasta
from conversor_nef import conversor
from conversor_nef.cli import main

AMOSTRA = os.environ.get("NEF_AMOSTRA")  # caminho opcional para um .NEF real


class RawFalso:
    """Imita o objeto do rawpy para testar sem precisar de um NEF de verdade."""

    def __init__(self, caminho):
        if Path(caminho).read_bytes() == b"quebrado":
            raise RuntimeError("arquivo corrompido")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def postprocess(self, **kwargs):
        assert kwargs["output_bps"] == 8
        return np.full((300, 400, 3), 128, dtype=np.uint8)


@pytest.fixture
def rawpy_falso(monkeypatch):
    monkeypatch.setattr(conversor.rawpy, "imread", RawFalso)


def criar(pasta: Path, nome: str, conteudo: bytes = b"nef") -> Path:
    caminho = pasta / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


def test_converte_para_jpeg_em_pasta_padrao(tmp_path, rawpy_falso):
    criar(tmp_path, "a.NEF")
    criar(tmp_path, "b.nef")
    criar(tmp_path, "nao_e_raw.txt")

    resumo = converter_pasta(tmp_path, processos=1)

    saida = tmp_path / "convertidos_jpeg"
    assert resumo.saida == saida
    assert resumo.contar("convertido") == 2
    assert sorted(p.name for p in saida.iterdir()) == ["a.jpg", "b.jpg"]
    with Image.open(saida / "a.jpg") as im:
        assert im.format == "JPEG" and im.size == (400, 300)


def test_png_redimensionado(tmp_path, rawpy_falso):
    criar(tmp_path, "a.nef")
    destino = tmp_path / "saida"

    converter_pasta(tmp_path, destino, Opcoes(formato="png", max_lado=200), processos=1)

    with Image.open(destino / "a.png") as im:
        assert im.format == "PNG" and im.size == (200, 150)


def test_recursivo_mantem_subpastas(tmp_path, rawpy_falso):
    criar(tmp_path, "viagem/dia1/x.nef")
    criar(tmp_path, "y.nef")

    assert converter_pasta(tmp_path, processos=1).contar("convertido") == 1
    resumo = converter_pasta(tmp_path, recursivo=True, processos=1)

    assert resumo.contar("convertido") == 1 and resumo.contar("pulado") == 1
    assert (tmp_path / "convertidos_jpeg/viagem/dia1/x.jpg").exists()


def test_pula_existentes_e_sobrescreve(tmp_path, rawpy_falso):
    criar(tmp_path, "a.nef")
    converter_pasta(tmp_path, processos=1)

    assert converter_pasta(tmp_path, processos=1).contar("pulado") == 1
    assert converter_pasta(tmp_path, processos=1, sobrescrever=True).contar("convertido") == 1


def test_erro_em_um_arquivo_nao_interrompe_o_lote(tmp_path, rawpy_falso):
    criar(tmp_path, "bom.nef")
    criar(tmp_path, "ruim.nef", b"quebrado")

    resumo = converter_pasta(tmp_path, processos=1)

    assert resumo.contar("convertido") == 1
    assert [r.origem.name for r in resumo.erros] == ["ruim.nef"]
    saida = tmp_path / "convertidos_jpeg"
    assert sorted(p.name for p in saida.iterdir()) == ["bom.jpg"]  # sem .tmp sobrando


def test_saida_dentro_da_entrada_nao_e_reprocessada(tmp_path, rawpy_falso):
    criar(tmp_path, "a.nef")
    criar(tmp_path, "convertidos_jpeg/antigo.nef")

    resumo = converter_pasta(tmp_path, recursivo=True, processos=1)

    assert [r.origem.name for r in resumo.resultados] == ["a.nef"]


def test_opcoes_invalidas():
    with pytest.raises(ValueError):
        Opcoes(formato="gif")
    with pytest.raises(ValueError):
        Opcoes(qualidade=0)
    assert Opcoes(formato="JPG").formato == "jpeg"


def test_cli(tmp_path, rawpy_falso, capsys):
    criar(tmp_path, "a.nef")
    assert main([str(tmp_path), "-f", "png", "-p", "1"]) == 0
    assert (tmp_path / "convertidos_png/a.png").exists()
    assert "1 convertidas" in capsys.readouterr().out
    assert main([str(tmp_path / "nao_existe")]) == 2


@pytest.mark.skipif(not AMOSTRA, reason="defina NEF_AMOSTRA=/caminho/foto.nef")
def test_nef_real_com_exif_e_paralelismo(tmp_path):
    for i in range(2):
        (tmp_path / f"foto{i}.nef").write_bytes(Path(AMOSTRA).read_bytes())

    resumo = converter_pasta(tmp_path, processos=2)

    assert resumo.contar("convertido") == 2, resumo.erros
    with Image.open(tmp_path / "convertidos_jpeg/foto0.jpg") as im:
        exif = im.getexif()
        assert exif.get(271)            # fabricante
        assert exif.get(274) == 1       # orientação já aplicada
        assert conversor._TAG_MAKERNOTE not in exif.get_ifd(conversor._IFD_EXIF)
