"""Conversor de fotos RAW Nikon (.NEF) para JPEG ou PNG."""

from .conversor import Opcoes, Resultado, Resumo, converter_arquivo, converter_pasta

__all__ = ["Opcoes", "Resultado", "Resumo", "converter_arquivo", "converter_pasta"]
__version__ = "1.0.0"
