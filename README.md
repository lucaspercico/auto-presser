# Auto Presser

**Gravador de teclado + auto-click de mouse** em um só app — use um, o outro, ou os dois no mesmo ciclo.

Interface moderna (dark), atalhos globais, panic stop e delays precisos. Feito para Windows.

[![Release](https://img.shields.io/github/v/release/lucaspercico/auto-presser?label=download)](https://github.com/lucaspercico/auto-presser/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Download

**→ [AutoPresser.exe](https://github.com/lucaspercico/auto-presser/releases/latest)**

1. Baixe o `.exe`  
2. Duplo clique para abrir  
3. Se o Windows avisar, *Mais informações* → *Executar mesmo assim* (app sem certificado de assinatura)

Configurações ficam em `settings.json` ao lado do executável.

---

## O que é?

| Módulo | Função |
|--------|--------|
| **Teclado** | Grava e reproduz sequência de teclas |
| **Mouse** | Auto-click (esquerdo / direito / meio) |
| **Híbrido** | Teclado + mouse no mesmo ciclo |

Use com responsabilidade. Não use para trapacear ou violar termos de terceiros.

---

## Uso rápido

| Tecla | Ação |
|-------|------|
| `F6` | Gravar / parar teclado |
| `F7` | Iniciar / parar |
| `F8` | Panic (para tudo) |

1. Ative **Teclado** e/ou **Mouse**  
2. Grave a sequência (`F6`)  
3. Ajuste intervalos e repetição  
4. Inicie com `F7`

---

## Código-fonte

```bash
git clone https://github.com/lucaspercico/auto-presser.git
cd auto-presser
pip install -r requirements.txt
python auto_presser.py
```

Sem CMD no Windows: duplo clique em `auto_presser.pyw`.

### Gerar o .exe

```bash
tools\build.bat
```

Saída: `dist\AutoPresser.exe`

---

## Estrutura

```
auto-presser/
├── auto_presser.py      # App
├── auto_presser.pyw     # Launcher sem console
├── assets/              # Ícone
├── tools/
│   ├── build.bat        # Build do .exe
│   └── make_icon.py
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Licença

MIT — veja [LICENSE](LICENSE).
