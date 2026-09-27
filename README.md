# Auto Presser

**Gravador de teclado + auto-click de mouse** em um só app — use um, o outro, ou os dois no mesmo ciclo.

Interface moderna (dark), atalhos globais, panic stop e delays precisos. Feito para ser estável e fácil de usar no Windows.

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

## Requisitos

- Windows 10/11 (recomendado)
- Python **3.10+**
- Dependências em `requirements.txt`

---

## Instalação

```bash
git clone https://github.com/lucaspercico/auto-presser.git
cd auto-presser
pip install -r requirements.txt
```

---

## Como usar

### Abrir sem janela de CMD (recomendado)

Dê **duplo clique** em:

```
auto_keyboard_presser.pyw
```

Isso usa `pythonw` e não abre o terminal.

### Ou pelo terminal

```bash
python auto_keyboard_presser.py
```

### Passo a passo rápido

1. No topo, ative **Teclado** e/ou **Mouse**
2. **Teclado:** pressione **F6** → digite a sequência → **F6** de novo para parar
3. **Mouse:** escolha botão, intervalo (ms) e posição (cursor atual ou X,Y)
4. Escolha **N vezes** ou **Contínuo**
5. **F7** inicia · **F7** de novo para · **F8** é o **Panic** (para tudo)

> Os atalhos funcionam com o app em segundo plano.

---

## Atalhos padrão

| Tecla | Ação |
|-------|------|
| `F6` | Gravar / parar gravação do teclado |
| `F7` | Iniciar / parar automação |
| `F8` | Panic — interrompe tudo imediatamente |

Você pode remapeá-los na seção **Atalhos globais**.

---

## Recursos

- Switches para Teclado / Mouse / ambos
- Lista editável (remover, limpar, reordenar)
- Salvar / abrir perfis JSON
- Intervalo mínimo de segurança (**10 ms**)
- Panic sempre disponível
- Atalhos **não** entram na gravação
- Debounce na UI durante gravação rápida
- Settings persistentes (`settings.json` local)
- Sem console ao usar o `.pyw`

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
├── requirements.txt
├── LICENSE
└── README.md
```

Arquivos locais (ignorados pelo git): `settings.json`, `profiles/`.

---

## Dependências

```
customtkinter
pynput
```

---

## Licença

MIT — veja [LICENSE](LICENSE).
