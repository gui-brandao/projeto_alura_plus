"""Interface de linha de comando do conversor."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__
from .conversor import Opcoes, Resultado, converter_pasta


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conversor-nef",
        description="Converte todas as fotos .NEF de uma pasta para JPEG ou PNG.",
    )
    p.add_argument("entrada", nargs="?", type=Path,
                   help="pasta com as fotos .NEF (omita para abrir a janela gráfica)")
    p.add_argument("-s", "--saida", type=Path,
                   help="pasta de destino (padrão: <entrada>/convertidos_<formato>)")
    p.add_argument("-f", "--formato", choices=["jpeg", "jpg", "png"], default="jpeg",
                   help="formato de saída (padrão: jpeg)")
    p.add_argument("-q", "--qualidade", type=int, default=92,
                   help="qualidade do JPEG, de 1 a 100 (padrão: 92)")
    p.add_argument("--max-lado", type=int, metavar="PX",
                   help="redimensiona para que o maior lado tenha no máximo PX pixels")
    p.add_argument("-r", "--recursivo", action="store_true",
                   help="inclui subpastas (a estrutura é mantida na saída)")
    p.add_argument("--sobrescrever", action="store_true",
                   help="reconverte arquivos que já existem na saída")
    p.add_argument("-p", "--processos", type=int, default=os.cpu_count(),
                   help="quantas fotos converter em paralelo (padrão: nº de núcleos)")
    p.add_argument("--sem-exif", action="store_true",
                   help="não copia os metadados (data, câmera, lente...)")
    p.add_argument("--sem-brilho-auto", action="store_true",
                   help="desliga o ajuste automático de brilho")
    p.add_argument("--wb-auto", action="store_true",
                   help="usa balanço de branco automático em vez do da câmera")
    p.add_argument("--gui", action="store_true", help="abre a janela gráfica")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _barra(feito: int, total: int, largura: int = 30) -> str:
    cheio = int(largura * feito / total) if total else largura
    return f"[{'#' * cheio}{'.' * (largura - cheio)}] {feito}/{total}"


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)

    if args.gui or args.entrada is None:
        from .gui import abrir_janela
        abrir_janela()
        return 0

    try:
        opcoes = Opcoes(
            formato=args.formato,
            qualidade=args.qualidade,
            max_lado=args.max_lado,
            balanco_camera=not args.wb_auto,
            brilho_auto=not args.sem_brilho_auto,
            manter_exif=not args.sem_exif,
        )
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    def progresso(feito: int, total: int, r: Resultado) -> None:
        marca = {"convertido": "ok", "pulado": "--", "erro": "!!"}[r.status]
        extra = f" ({r.mensagem})" if r.mensagem else ""
        print(f"{_barra(feito, total)}  {marca} {r.origem.name}{extra}", flush=True)

    inicio = time.perf_counter()
    try:
        resumo = converter_pasta(
            args.entrada, args.saida, opcoes,
            recursivo=args.recursivo,
            sobrescrever=args.sobrescrever,
            processos=args.processos,
            ao_progredir=progresso,
        )
    except NotADirectoryError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    if not resumo.resultados:
        print("Nenhum arquivo .NEF encontrado.")
        return 1

    duracao = time.perf_counter() - inicio
    print(
        f"\nConcluído em {duracao:.1f}s: {resumo.contar('convertido')} convertidas, "
        f"{resumo.contar('pulado')} puladas, {resumo.contar('erro')} com erro."
    )
    print(f"Arquivos em: {resumo.saida}")
    for r in resumo.erros:
        print(f"  ERRO {r.origem}: {r.mensagem}", file=sys.stderr)
    return 1 if resumo.erros else 0
