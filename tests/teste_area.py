"""
Testes: estilo branco como padrão, novos modelos de área e montagem de
área livre pela IA (simulada). Rodar: python tests/teste_area.py
"""
import os, sys, json, types, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_area_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="a"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", LIMITE_SUGESTAO_AREA_MES="2")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

class B:
    def __init__(s, t): s.type = "text"; s.text = t
CHAMADAS = []
class M:
    def create(s, **kw):
        CHAMADAS.append(kw["messages"][0]["content"])
        out = {"area": "Direito Agrário", "frentes": [{"nome": "Posse e terra", "descricao": "Usucapião rural — conflitos"},
               {"nome": "Crédito rural", "descricao": "Financiamentos"}], "publico": "QUEM É O PÚBLICO\n- Produtores rurais — pequenos e médios"}
        return types.SimpleNamespace(content=[B(json.dumps(out, ensure_ascii=False))], usage=types.SimpleNamespace(input_tokens=500, output_tokens=400, server_tool_use=None))
g._cliente = lambda: types.SimpleNamespace(messages=M())

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
opcoes = dict(dono.get("/api/opcoes").json["modelos_perfil"])
ok(all(k in opcoes for k in ["tributario", "empresarial", "criminal", "imobiliario", "saude", "trabalhista", "familia"]), "novos modelos de área disponíveis")
ok(list(opcoes)[-1] == "em_branco" and "IA" in opcoes["em_branco"], "\"Outra área (a IA monta)\" é a última opção")

pid = dono.post("/api/perfis", json={"nome_exibicao": "Tributarista", "modelo": "tributario"}).json["id"]
p = A.buscar_perfil(pid)
ok(p["estilo_visual"] == "claro", "perfil novo nasce com estilo branco")
ok(p["area"] == "Direito Tributário" and len(p["frentes"]) == 3, "modelo tributário preenche área e temas")
ok(not CHAMADAS, "modelo pronto não gasta IA")

tok = dono.post("/api/admin/usuarios", json={"nome": "Cli", "email": "c@x.com", "dias_acesso": 7}).json["link_convite"].split("/convite/")[1]
cli = A.app.test_client(); cli.post(f"/api/convite/{tok}", json={"senha": "senha12345"})
r = cli.post("/api/perfis", json={"nome_exibicao": "Dr. Agro", "modelo": "em_branco", "area_outra": "direito agrario"})
pa = r.json["id"]; p = A.buscar_perfil(pa)
ok(r.status_code == 201 and r.json["aviso"] is None, "área livre: perfil criado sem aviso")
ok(p["area"] == "Direito Agrário" and p["frentes"][0]["nome"] == "Posse e terra", "área livre: a IA montou área e temas")
ok("—" not in json.dumps(p, ensure_ascii=False), "sugestão sem travessões")

r = cli.post(f"/api/perfis/{pa}/sugerir_area", json={"area": "Direito Agrário"})
ok(r.status_code == 200 and r.json["frentes"], "botão Sugerir com IA devolve sugestão")
ok(A.buscar_perfil(pa)["publico"] == p["publico"], "sugestão NÃO salva sozinha (a pessoa revisa)")
r = cli.post(f"/api/perfis/{pa}/sugerir_area", json={"area": "Direito Agrário"})
ok(r.status_code == 429, "limite mensal de sugestões pro cliente (2 no teste)")
ok(dono.post(f"/api/perfis/{pa}/sugerir_area", json={"area": "X"}).status_code == 200, "dono não tem limite de sugestões")
outro = A.app.test_client()
ok(outro.post(f"/api/perfis/{pa}/sugerir_area", json={"area": "X"}).status_code == 401, "sem login não sugere")
tok2 = dono.post("/api/admin/usuarios", json={"nome": "Outro", "email": "o@x.com", "dias_acesso": 7}).json["link_convite"].split("/convite/")[1]
outro.post(f"/api/convite/{tok2}", json={"senha": "senha12345"})
ok(outro.post(f"/api/perfis/{pa}/sugerir_area", json={"area": "X"}).status_code == 404, "outro cliente não usa perfil alheio")
painel = {u["email"]: u for u in dono.get("/api/admin/usuarios").json["usuarios"]}
ok(painel["c@x.com"]["custo_mes_usd"] > 0, "custo das sugestões aparece no painel do dono")

class Falha:
    def create(s, **kw): raise RuntimeError("fora do ar")
g._cliente = lambda: types.SimpleNamespace(messages=Falha())
r = dono.post("/api/perfis", json={"nome_exibicao": "Z", "modelo": "em_branco", "area_outra": "Direito Espacial"})
ok(r.status_code == 201 and r.json["aviso"] and A.buscar_perfil(r.json["id"])["area"] == "Direito Espacial",
   "se a IA falhar, o perfil é criado mesmo assim, com aviso")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
