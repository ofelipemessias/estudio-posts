"""
Testes da limpeza do texto dos slides gerados pela IA: tira "Slide 3",
numeração "2/7", travessões e quebras de linha no meio da frase, sem
estragar destaques (**palavra**) nem listas feitas de propósito.
Rodar: python tests/teste_limpeza_slides.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from motor.gerar_post import _limpar_slide as L

CASOS = [
    ("Slide 3\n\nEssa proteção chama **autenticação em dois fatores.**\n\nMesmo que alguém descubra sua senha,\nprecisa de um código extra pra entrar.",
     "Essa proteção chama **autenticação em dois fatores.**\n\nMesmo que alguém descubra sua senha, precisa de um código extra pra entrar."),
    ("Slide 1: **34 bilhões de tentativas de golpe.**\n\nEm um único ano.", "**34 bilhões de tentativas de golpe.**\n\nEm um único ano."),
    ("**Slide 2**\nEu vejo isso todo dia:\n\nA pessoa perde o acesso.", "Eu vejo isso todo dia:\n\nA pessoa perde o acesso."),
    ("**Slide 4:** Mas isso sozinho não resolve.", "Mas isso sozinho não resolve."),
    ("slide 5 - Também confira a **Central de Contas.**", "Também confira a **Central de Contas.**"),
    ("Ative agora:\n- dois fatores\n- e-mail atualizado", "Ative agora:\n- dois fatores\n- e-mail atualizado"),
    ("Passos:\n1. Ative os dois fatores\n2. Atualize o e-mail", "Passos:\n1. Ative os dois fatores\n2. Atualize o e-mail"),
    ("2/7 Não é falta de sorte — é falta de proteção.", "Não é falta de sorte, é falta de proteção."),
    ("Slides de aula também podem virar post.", "Slides de aula também podem virar post."),
    ("O que eu sempre digo pra quem vende pelo Instagram\nou usa o WhatsApp no trabalho:",
     "O que eu sempre digo pra quem vende pelo Instagram ou usa o WhatsApp no trabalho:"),
]
falhas = 0
for entrada, esperado in CASOS:
    obtido = L(entrada)
    ok = obtido == esperado
    falhas += not ok
    print(("OK      " if ok else "FALHOU  ") + repr(entrada[:50]) + ("" if ok else f"\n   obtido: {obtido!r}"))
print()
print(f"{falhas} falha(s)." if falhas else "Todos os testes passaram.")
sys.exit(1 if falhas else 0)
