"""
Testes da tela de escolha de perfil: resumo de uso, cor da marca,
completude, situação do cliente e acesso à foto de perfil.
Rodar a partir da raiz do projeto: python tests/teste_perfis.py
"""
import os, sys, io, json, types, time, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_perfis_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="p"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", DONO_NOME="Dono")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g
from PIL import Image
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

class B:
    def __init__(s, t): s.type = "text"; s.text = t
class M:
    def create(s, **kw):
        out = {"titulo_interno": "T", "slides": ["a"], "legenda": "l", "hashtags": [], "alertas": []}
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, server_tool_use=None))
g._cliente = lambda: types.SimpleNamespace(messages=M())

def png():
    b = io.BytesIO(); Image.new("RGB", (60, 60), "red").save(b, "PNG"); b.seek(0); return b

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
def convidar(nome, email):
    tok = dono.post("/api/admin/usuarios", json={"nome": nome, "email": email, "dias_acesso": 30}).json["link_convite"].split("/convite/")[1]
    c = A.app.test_client(); c.post(f"/api/convite/{tok}", json={"senha": "senha12345"}); return c
ana, beto = convidar("Ana", "ana@x.com"), convidar("Beto", "beto@x.com")
pa = ana.post("/api/perfis", json={"nome_exibicao": "Dra. Ana", "modelo": "previdenciario"}).json["id"]
pb = beto.post("/api/perfis", json={"nome_exibicao": "Dr. Beto", "modelo": "trabalhista"}).json["id"]
pd = dono.post("/api/perfis", json={"nome_exibicao": "Perfil do dono", "modelo": "em_branco"}).json["id"]

ok(ana.get(f"/api/perfis/{pa}/avatar").status_code == 404, "sem foto: 404")
ana.post(f"/api/perfis/{pa}/avatar", data={"avatar": (png(), "f.png")}, content_type="multipart/form-data")
ok(ana.get(f"/api/perfis/{pa}/avatar").status_code == 200, "dona do perfil vê a própria foto")
ok(beto.get(f"/api/perfis/{pa}/avatar").status_code == 404, "outro cliente NÃO vê a foto da Ana")
ok(A.app.test_client().get(f"/api/perfis/{pa}/avatar").status_code == 401, "sem login NÃO vê foto")
ok(dono.get(f"/api/perfis/{pa}/avatar").status_code == 200, "dono vê a foto de qualquer perfil")

ana.post(f"/api/perfis/{pa}/posts", json={"formato": "post_unico", "tema": "x"}); time.sleep(1.2)
lista = {p["id"]: p for p in dono.get("/api/perfis").json}
a = lista[pa]
ok(a["posts_total"] == 1 and a["posts_mes"] == 1 and a["ultimo_post_em"], "resumo de uso do perfil")
ok(a["avatar_versao"] and a["cor_destaque"].startswith("#") and a["cor_fundo"].startswith("#"), "foto e cores da marca no resumo")
ok(0 <= a["completo_pct"] <= 100 and isinstance(a["falta"], list), "percentual de perfil completo")
ok(a["de_cliente"] and a["cliente_situacao"] == "ativo", "situação do acesso do cliente")
ok(not lista[pd]["de_cliente"] and "cliente_situacao" not in lista[pd], "perfil do dono não é de cliente")
ok([p["id"] for p in ana.get("/api/perfis").json] == [pa], "cliente só recebe o próprio perfil no resumo")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
