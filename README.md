# Auto Presser

**Gravador de teclado + auto-click de mouse** em um só app — use um, o outro, ou os dois no mesmo ciclo.

Interface moderna (dark), atalhos globais, panic stop e delays precisos. Feito para ser estável e fácil de usar no Windows.

[![Release](https://img.shields.io/github/v/release/lucaspercico/auto-presser?label=download)](https://github.com/lucaspercico/auto-presser/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Download (executável)

Não precisa instalar Python. Baixe o `.exe` na última release:

**→ [AutoPresser.exe (Releases)](https://github.com/lucaspercico/auto-presser/releases/latest)**

1. Baixe `AutoPresser.exe`
2. Dê duplo clique para abrir (sem janela de CMD)
3. Se o Windows Defender pedir confirmação, escolha *Mais informações* → *Executar mesmo assim* (comum em apps novos sem assinatura digital)

O app salva `settings.json` e a pasta `profiles/` **ao lado do .exe**.

---

## O que é?

Ferramenta de automação leve para:

| Módulo | O que faz |
|--------|-----------|
| **Teclado** | Grava uma sequência de teclas e reproduz com intervalo configurável |
| **Mouse** | Auto-click (esquerdo / direito / meio) no cursor ou em posição fixa |
| **Híbrido** | Em cada ciclo: toca a sequência de teclas e depois os cliques |

Ideal para testes de UI, macros simples e tarefas repetitivas. **Não** substitui ferramentas anti-cheat — use com responsabilidade.

---

## Como usar

1. No topo, ative **Teclado** e/ou **Mouse**
2. **Teclado:** pressione **F6** → digite a sequência → **F6** de novo para parar
3. **Mouse:** escolha botão, intervalo (ms) e posição (cursor atual ou X,Y)
4. Escolha **N vezes** ou **Contínuo**
5. **F7** inicia · **F7** de novo para · **F8** é o **Panic** (para tudo)

> Os atalhos funcionam com o app em segundo plano.

### Atalhos padrão

| Tecla | Ação |
|-------|------|
| `F6` | Gravar / parar gravação do teclado |
| `F7` | Iniciar / parar automação |
| `F8` | Panic — interrompe tudo imediatamente |

---

## Rodar pelo código-fonte

### Requisitos

- Windows 10/11
- Python **3.10+**

```bash
git clone https://github.com/lucaspercico/auto-presser.git
cd auto-presser
pip install -r requirements.txt
```

### Abrir

```bash
# Sem janela de CMD (recomendado)
auto_keyboard_presser.pyw

# Ou pelo terminal
python auto_keyboard_presser.py
```

---

## Gerar o .exe você mesmo

No Windows:

```bash
build.bat
```

O arquivo sai em `dist\AutoPresser.exe` (onefile, sem console).

Equivalente manual:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name AutoPresser ^
  --collect-all customtkinter ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  auto_keyboard_presser.py
```

---

## Recursos

- Switches para Teclado / Mouse / ambos
- Lista editável (remover, limpar, reordenar)
- Salvar / abrir perfis JSON
- Intervalo mínimo de segurança (**10 ms**)
- Panic sempre disponível
- Atalhos **não** entram na gravação
- Layout compacto sem rolagem nos controles
- Settings persistentes ao lado do executável / script

---

## Segurança e boas práticas

- Use o **Panic (F8)** se algo sair do controle
- Prefira intervalos ≥ 50 ms no dia a dia
- Em jogos/apps protegidos, pode ser necessário **executar como administrador**
- Não use para trapacear ou violar termos de serviço de terceiros

---

## Estrutura

```
auto-presser/
├── auto_keyboard_presser.py    # App principal
├── auto_keyboard_presser.pyw   # Launcher sem CMD
├── build.bat                   # Gera o .exe
├── requirements.txt
├── LICENSE
└── README.md
```

Arquivos locais (ignorados pelo git): `settings.json`, `profiles/`, `dist/`, `build/`.

---

## Licença

MIT — veja [LICENSE](LICENSE).
