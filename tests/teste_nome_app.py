"""
Testes do nome configurável (APP_NOME): aparece na página, no título e
na logo, e nomes com caracteres especiais nunca viram HTML/JS.
Rodar a partir da raiz do projeto: python tests/teste_nome_app.py
"""
import os, sys, re, tempfile, importlib, json, subprocess
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

def carregar(nome):
    os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_nome_"), SECRET_KEY="n"*40, ANTHROPIC_API_KEY="fake")
    if nome is None:
        os.environ.pop("APP_NOME", None)
    else:
        os.environ["APP_NOME"] = nome
    import app as A
    return importlib.reload(A)

A = carregar(None)
html = A.app.test_client().get("/").get_data(as_text=True)
ok("<title>Estúdio de Posts</title>" in html, "sem APP_NOME: usa o nome padrão")
ok("Estúdio de <span>Posts</span>" in html, "logo padrão com destaque na última palavra")
ok("{{" not in html, "nenhum marcador sobrando na página")

A = carregar("Advoga+")
c = A.app.test_client()
html = c.get("/").get_data(as_text=True)
ok("<title>Advoga+</title>" in html, "título da aba: Advoga+")
ok(html.count("Advoga<span>+</span>") == 3, "logo com o + destacado (login, convite e topo)")
ok('const APP_NOME = "Advoga+";' in html, "nome disponível pro JavaScript (mensagem do WhatsApp)")
ok("Advoga+" in c.get("/convite/qualquer").get_data(as_text=True), "página de convite também usa o nome")

A = carregar('</script><script>alert(1)</script>"&')
html = A.app.test_client().get("/").get_data(as_text=True)
ok("<script>alert(1)" not in html, "nome malicioso não vira HTML/JS")
ok("&lt;/script&gt;" in html, "nome malicioso aparece escapado no título")
# o JavaScript da página continua válido
js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
arq = os.path.join(tempfile.mkdtemp(), "p.js"); open(arq, "w").write(js)
try:
    r = subprocess.run(["node", "--check", arq], capture_output=True, text=True)
    ok(r.returncode == 0, "JavaScript da página continua válido com nome estranho")
except FileNotFoundError:
    print("(node não instalado: pulando checagem de sintaxe do JS)")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
