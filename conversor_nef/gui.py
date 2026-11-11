"""Janela simples (Tkinter) para escolher a pasta e converter as fotos."""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

from .conversor import Opcoes, converter_pasta


def abrir_janela() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        raise SystemExit(
            "Tkinter não está instalado. Use a linha de comando "
            "(conversor-nef PASTA) ou instale o pacote python3-tk."
        )

    raiz = tk.Tk()
    raiz.title("Conversor NEF → JPEG/PNG")
    raiz.resizable(False, False)
    quadro = ttk.Frame(raiz, padding=14)
    quadro.grid()

    entrada = tk.StringVar()
    saida = tk.StringVar()
    formato = tk.StringVar(value="jpeg")
    qualidade = tk.IntVar(value=92)
    max_lado = tk.StringVar(value="")
    recursivo = tk.BooleanVar(value=False)
    exif = tk.BooleanVar(value=True)
    status = tk.StringVar(value="Escolha a pasta com as fotos .NEF")
    eventos: queue.Queue = queue.Queue()

    def escolher_entrada() -> None:
        pasta = filedialog.askdirectory(title="Pasta com as fotos .NEF")
        if pasta:
            entrada.set(pasta)
            if not saida.get():
                saida.set(str(Path(pasta) / f"convertidos_{formato.get()}"))

    def escolher_saida() -> None:
        pasta = filedialog.askdirectory(title="Pasta de destino")
        if pasta:
            saida.set(pasta)

    linha = 0
    ttk.Label(quadro, text="Pasta das fotos:").grid(row=linha, column=0, sticky="w")
    ttk.Entry(quadro, textvariable=entrada, width=50).grid(row=linha, column=1, padx=6)
    ttk.Button(quadro, text="Escolher…", command=escolher_entrada).grid(row=linha, column=2)
    linha += 1
    ttk.Label(quadro, text="Salvar em:").grid(row=linha, column=0, sticky="w", pady=4)
    ttk.Entry(quadro, textvariable=saida, width=50).grid(row=linha, column=1, padx=6)
    ttk.Button(quadro, text="Escolher…", command=escolher_saida).grid(row=linha, column=2)

    linha += 1
    opc = ttk.LabelFrame(quadro, text="Opções", padding=8)
    opc.grid(row=linha, column=0, columnspan=3, sticky="ew", pady=8)
    ttk.Radiobutton(opc, text="JPEG", value="jpeg", variable=formato).grid(row=0, column=0)
    ttk.Radiobutton(opc, text="PNG", value="png", variable=formato).grid(row=0, column=1)
    ttk.Label(opc, text="Qualidade JPEG:").grid(row=0, column=2, padx=(16, 4))
    ttk.Spinbox(opc, from_=1, to=100, textvariable=qualidade, width=5).grid(row=0, column=3)
    ttk.Label(opc, text="Maior lado (px, vazio = original):").grid(row=1, column=0,
                                                                  columnspan=3, sticky="w")
    ttk.Entry(opc, textvariable=max_lado, width=7).grid(row=1, column=3, pady=4)
    ttk.Checkbutton(opc, text="Incluir subpastas", variable=recursivo).grid(
        row=2, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(opc, text="Manter metadados (EXIF)", variable=exif).grid(
        row=2, column=2, columnspan=2, sticky="w")

    linha += 1
    barra = ttk.Progressbar(quadro, length=460, mode="determinate")
    barra.grid(row=linha, column=0, columnspan=3, pady=(4, 2))
    linha += 1
    ttk.Label(quadro, textvariable=status).grid(row=linha, column=0, columnspan=3, sticky="w")
    linha += 1
    botao = ttk.Button(quadro, text="Converter")
    botao.grid(row=linha, column=0, columnspan=3, pady=(10, 0))

    def trabalhar(opcoes: Opcoes, origem: str, destino: str, rec: bool) -> None:
        try:
            resumo = converter_pasta(
                origem, destino or None, opcoes, recursivo=rec,
                processos=os.cpu_count(),
                ao_progredir=lambda f, t, r: eventos.put(("progresso", f, t, r)),
            )
            eventos.put(("fim", resumo))
        except Exception as exc:
            eventos.put(("falha", exc))

    def acompanhar() -> None:
        try:
            while True:
                ev = eventos.get_nowait()
                if ev[0] == "progresso":
                    _, feito, total, r = ev
                    barra["maximum"] = total
                    barra["value"] = feito
                    status.set(f"{feito}/{total}  {r.origem.name}: {r.status}")
                else:
                    botao.state(["!disabled"])
                    if ev[0] == "falha":
                        messagebox.showerror("Erro", str(ev[1]))
                        return
                    resumo = ev[1]
                    if not resumo.resultados:
                        status.set("Nenhum arquivo .NEF encontrado nessa pasta.")
                        return
                    msg = (f"{resumo.contar('convertido')} convertidas, "
                           f"{resumo.contar('pulado')} já existiam, "
                           f"{resumo.contar('erro')} com erro.")
                    status.set(msg)
                    detalhes = "\n".join(f"{r.origem.name}: {r.mensagem}"
                                         for r in resumo.erros[:10])
                    messagebox.showinfo("Concluído", msg + ("\n\n" + detalhes if detalhes else ""))
                    return
        except queue.Empty:
            pass
        raiz.after(100, acompanhar)

    def iniciar() -> None:
        if not entrada.get():
            messagebox.showwarning("Atenção", "Escolha a pasta com as fotos.")
            return
        try:
            lado = int(max_lado.get()) if max_lado.get().strip() else None
            opcoes = Opcoes(formato=formato.get(), qualidade=int(qualidade.get()),
                            max_lado=lado, manter_exif=exif.get())
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Opção inválida", str(exc))
            return
        botao.state(["disabled"])
        barra["value"] = 0
        status.set("Procurando fotos…")
        threading.Thread(target=trabalhar, daemon=True,
                         args=(opcoes, entrada.get(), saida.get(), recursivo.get())).start()
        raiz.after(100, acompanhar)

    botao.configure(command=iniciar)
    raiz.mainloop()
