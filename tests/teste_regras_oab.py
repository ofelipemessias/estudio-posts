"""
Testes da opção "Seguir as regras de publicidade da OAB" por perfil:
ligada por padrão; desligada troca as instruções da IA (posts e radar),
mas mantém as regras gerais (não inventar dados, não prometer).
Rodar: python tests/teste_regras_oab.py
"""
import os, sys, json, types, time, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_oab_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="o"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

SYS = []
class B:
    def __init__(s, t): s.type = "text"; s.text = t
class M:
    def create(s, **kw):
        SYS.append((kw["system"], kw["messages"][0]["content"]))
        if "pautas" in kw["system"] or "PAUTAS" in kw["system"]:
            out = {"pautas": [{"frente": "Geral", "titulo": "t", "resumo": "r", "por_que_importa": "p", "angulo": "a", "formato_sugerido": "carrossel"}]}
        else:
            out = {"titulo_interno": "T", "slides": ["a", "b"], "legenda": "l", "hashtags": [], "alertas": []}
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, server_tool_use=None))
g._cliente = lambda: types.SimpleNamespace(messages=M())

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
pid = dono.post("/api/perfis", json={"nome_exibicao": "Sua Conta Segura", "modelo": "em_branco"}).json["id"]
p = [x for x in dono.get("/api/perfis").json if x["id"] == pid][0]
ok(p["regras_oab"] is True, "perfil novo: regras da OAB ligadas por padrão")

dono.post(f"/api/perfis/{pid}/posts", json={"formato": "carrossel", "tema": "x", "cta": "Salve este post."}); time.sleep(1.2)
sistema, pedido = SYS[-1]
ok("Provimento 205/2021" in sistema and "redator de redes sociais de um advogado" in sistema, "ligado: instruções da OAB e redator de advogado")
ok("CTA permitido pelas regras da OAB" in sistema and "ajuste se ferir a regra da OAB" in pedido, "ligado: CTA sob as regras da OAB")

p.update({"regras_oab": False})
ok(dono.put(f"/api/perfis/{pid}", json=p).status_code == 200, "salva com as regras desligadas")
ok([x for x in dono.get("/api/perfis").json if x["id"] == pid][0]["regras_oab"] is False, "opção desligada fica gravada")
dono.post(f"/api/perfis/{pid}/posts", json={"formato": "reels", "tema": "x", "cta": "Me chama no direct que eu te ajudo."}); time.sleep(1.2)
sistema, pedido = SYS[-1]
ok("Provimento 205/2021" not in sistema and "REGRAS DE COMUNICAÇÃO" in sistema, "desligado: troca pelas regras gerais")
ok("não invente dados" in sistema and "não faça promessa" in sistema, "desligado: continua proibindo inventar dados e prometer")
ok("profissional ou de uma marca" in sistema and "regra da OAB" not in sistema, "desligado: redator genérico e alertas sem OAB")
ok("CTA claro e direto" in sistema and pedido.count("CTA DESEJADO: Me chama no direct") == 1, "desligado: CTA livre (ex.: chamar no direct)")

dono.post(f"/api/perfis/{pid}/pautas", json={"modo": "ideias"}); time.sleep(1.5)
sistema, _ = SYS[-1]
ok("Provimento 205/2021" not in sistema and "profissional ou de uma marca" in sistema, "radar de pautas também respeita a opção")

p.update({"regras_oab": True}); dono.put(f"/api/perfis/{pid}", json=p)
dono.post(f"/api/perfis/{pid}/posts", json={"formato": "post_unico", "tema": "x"}); time.sleep(1.2)
ok("Provimento 205/2021" in SYS[-1][0], "religar volta as regras da OAB")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
