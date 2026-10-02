"""
Testes dos estilos de arte (tweet, editorial, minimalista) e do formato
Story (1080x1920): padrão do perfil, escolha por post, redesenho ao editar,
prévia e bloqueio da publicação automática de stories.
Rodar: python tests/teste_estilos.py
"""
import os, sys, io, json, time, types, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_est_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="e"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", EMAILS_AUTOMATICOS="0", ZERNIO_API_KEY="sk")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as G, render_post as R
from PIL import Image
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

PROMPTS = []
class B:
    def __init__(s, t): s.type = "text"; s.text = t
class M:
    def create(s, **kw):
        PROMPTS.append(kw["system"])
        out = {"titulo_interno": "T", "slides": ["Tela **um**\\n\\ncom texto", "Tela dois", "Tela três"], "legenda": "l", "hashtags": [], "alertas": []}
        out["slides"] = ["Tela **um**\n\ncom texto", "Tela dois", "Tela três"]
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, server_tool_use=None))
G._cliente = lambda: types.SimpleNamespace(messages=M())
tamanho = lambda post_id, n=1: Image.open(A.PASTA_POSTS / post_id / f"slide_{n:02d}.png").size

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
op = dono.get("/api/opcoes").json
ok([k for k, _ in op["modelos_arte"]] == ["tweet", "editorial", "minimal"] and "story" in dict(op["formatos"]), "opções: 3 estilos e o formato Story")
pid = dono.post("/api/perfis", json={"nome_exibicao": "Dra. Ana", "modelo": "digital_consumidor"}).json["id"]
p = [x for x in dono.get("/api/perfis").json if x["id"] == pid][0]
ok(p["modelo_arte"] == "tweet", "perfil novo: estilo tweet por padrão")
p["modelo_arte"] = "editorial"; dono.put(f"/api/perfis/{pid}", json=p)
ok([x for x in dono.get("/api/perfis").json if x["id"] == pid][0]["modelo_arte"] == "editorial", "estilo padrão do perfil é salvo")
p["modelo_arte"] = "inventado"; dono.put(f"/api/perfis/{pid}", json=p)
ok([x for x in dono.get("/api/perfis").json if x["id"] == pid][0]["modelo_arte"] == "tweet", "estilo inválido volta pro tweet")
p["modelo_arte"] = "editorial"; dono.put(f"/api/perfis/{pid}", json=p)

def gerar(**kw):
    r = dono.post(f"/api/perfis/{pid}/posts", json={"tema": "x", **kw}); time.sleep(1.3)
    return r.json["id"]

c1 = gerar(formato="carrossel")
ok(A.buscar_post(c1)["opcoes"].get("modelo_arte") == "editorial", "post usa o estilo padrão do perfil")
ok(tamanho(c1) == (1080, 1350), "carrossel: 1080x1350")
c2 = gerar(formato="carrossel", modelo_arte="minimal")
ok(tamanho(c2) == (1080, 1350) and A.buscar_post(c2)["opcoes"]["modelo_arte"] == "minimal", "estilo escolhido no post (minimalista) vale só pra ele")
st = gerar(formato="story")
ok(tamanho(st) == (1080, 1920) and tamanho(st, 3) == (1080, 1920), "story: todas as telas em 1080x1920")
ok("FORMATO: STORIES" in PROMPTS[-1], "IA recebe as regras de stories")
# editar e redesenhar mantém tela e estilo
post = A.buscar_post(st)
r = dono.put(f"/api/posts/{st}/textos", json={"slides": ["Nova **tela**", "Outra", "Mais uma"], "legenda": "x"})
ok(r.status_code == 200 and tamanho(st) == (1080, 1920), "editar um story redesenha em 1080x1920")
# prévia
prev = dono.post(f"/api/perfis/{pid}/previa", json={"modelo_arte": "minimal", "tela": "story"})
ok(prev.status_code == 200 and Image.open(io.BytesIO(prev.data)).size == (1080, 1920), "prévia aceita estilo e tela")
# publicação automática de story bloqueada
r = dono.post(f"/api/posts/{st}/publicar", json={})
ok(r.status_code == 400 and "Postar pelo celular" in r.json["erro"], "story não publica automático (orienta usar o celular)")
# render direto: os 3 estilos nos 2 tamanhos
d = tempfile.mkdtemp()
for modelo in R.MODELOS_ARTE:
    for tela, tam in (("feed", (1080, 1350)), ("story", (1080, 1920))):
        cam = os.path.join(d, f"{modelo}_{tela}.png")
        R.desenhar_slide("Um **título** forte\n\nE um texto de apoio um pouco maior pra quebrar linha.", {"nome": "Ana", "handle": "ana"},
                         R.montar_paleta("claro", {}), cam, modelo, tela, 1, 3)
        ok(Image.open(cam).size == tam, f"desenho {modelo} / {tela} no tamanho certo")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
