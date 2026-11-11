# Conversor NEF → JPEG / PNG

Converte em lote as fotos RAW da Nikon (`.NEF` / `.NRW`) para **JPEG** ou **PNG**.
Você indica a pasta com as fotos e o programa cria uma nova pasta com as imagens
convertidas. Os originais não são alterados.

## Como funciona

```
pasta_das_fotos/
├── DSC_0001.NEF
├── DSC_0002.NEF
└── convertidos_jpeg/        ← criada pelo conversor
    ├── DSC_0001.jpg
    └── DSC_0002.jpg
```

- **Decodificação do RAW:** [rawpy](https://github.com/letmaik/rawpy), que usa o
  LibRaw (a mesma base de vários editores de foto). Aplica o balanço de branco
  da câmera, a correção de cor e a rotação certa da foto.
- **Gravação:** [Pillow](https://python-pillow.org/), em JPEG (qualidade
  ajustável, sem subamostragem de cor) ou PNG (sem perdas).
- **Metadados:** data da foto, câmera, lente, ISO, abertura, velocidade e GPS
  são copiados para o arquivo final.
- **Rapidez:** converte várias fotos ao mesmo tempo, uma por núcleo do processador.
- **Seguro para repetir:** fotos já convertidas são puladas, então dá para
  rodar de novo depois de adicionar fotos novas. Uma foto com defeito não
  interrompe o lote: ela é listada no final.

## Instalação

Precisa do Python 3.9 ou mais novo.

```bash
git clone https://github.com/gui-brandao/projeto_alura_plus.git
cd projeto_alura_plus
python -m venv .venv
# Windows: .venv\Scripts\activate    |    macOS/Linux: source .venv/bin/activate
pip install -e .
```

## Uso

### Janela gráfica

```bash
conversor-nef
```

Clique em **Escolher…**, selecione a pasta das fotos, ajuste as opções e clique
em **Converter**.

### Linha de comando

```bash
# JPEG na pasta padrão (<pasta>/convertidos_jpeg)
conversor-nef "C:\Users\voce\Fotos\Viagem"

# PNG em outra pasta, incluindo subpastas
conversor-nef ~/Fotos/Viagem -f png -s ~/Fotos/Viagem_PNG -r

# JPEG menor para compartilhar (maior lado com 2048 px, qualidade 85)
conversor-nef ~/Fotos/Viagem --max-lado 2048 -q 85
```

| Opção | O que faz |
|---|---|
| `-s, --saida PASTA` | pasta de destino (padrão: `<entrada>/convertidos_<formato>`) |
| `-f, --formato jpeg\|png` | formato de saída (padrão: `jpeg`) |
| `-q, --qualidade N` | qualidade do JPEG, de 1 a 100 (padrão: 92) |
| `--max-lado PX` | reduz a imagem para que o maior lado tenha no máximo PX pixels |
| `-r, --recursivo` | inclui subpastas e mantém a mesma estrutura na saída |
| `--sobrescrever` | reconverte fotos que já existem na saída |
| `-p, --processos N` | quantas fotos converter em paralelo (padrão: nº de núcleos) |
| `--sem-exif` | não copia os metadados |
| `--sem-brilho-auto` | desliga o ajuste automático de brilho |
| `--wb-auto` | balanço de branco automático em vez do da câmera |

Também funciona sem instalar o comando: `python -m conversor_nef PASTA`.

### Como biblioteca

```python
from conversor_nef import Opcoes, converter_pasta

resumo = converter_pasta("~/Fotos/Viagem", opcoes=Opcoes(formato="png"))
print(resumo.contar("convertido"), "fotos convertidas em", resumo.saida)
```

## Estrutura do projeto

```
conversor_nef/
├── conversor.py   # núcleo: busca os arquivos, decodifica, grava e copia o EXIF
├── cli.py         # linha de comando
├── gui.py         # janela Tkinter
└── __main__.py    # permite rodar com python -m conversor_nef
tests/
└── test_conversor.py
```

## Testes

```bash
pip install -e ".[dev]"
pytest
# para testar também com uma foto real:
NEF_AMOSTRA=/caminho/para/foto.NEF pytest
```

## Observações

- No Linux, a janela gráfica precisa do Tkinter (`sudo apt install python3-tk`).
  No Windows e no macOS ele já vem com o Python.
- O PNG é gravado com 8 bits por canal. Ele não tem perdas, mas os arquivos
  ficam bem maiores que os JPEG.
- O bloco proprietário de metadados da Nikon (MakerNote) não é copiado, porque
  costuma passar do limite de tamanho do EXIF em JPEG.
