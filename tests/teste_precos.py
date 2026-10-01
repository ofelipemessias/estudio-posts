"""
Testes de preço: preço de fundador (com vagas), preço cheio quando as
vagas acabam, plano anual (12 meses de acesso) e preço travado.
Rodar: python tests/teste_precos.py
"""
import os, sys, tempfile, sqlite3
from datetime import datetime, timedelta
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "p" * 40
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_preco_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="r"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", ASAAS_API_KEY="$aact_t", ASAAS_WEBHOOK_TOKEN=TOKEN,
                  PRECO_ESSENCIAL="147", PRECO_COMPLETO="197", PRECO_FUNDADOR_ESSENCIAL="97", PRECO_FUNDADOR_COMPLETO="147",
                  FUNDADOR_VAGAS="2", MESES_ANUAL="10")
sys.path.insert(0, RAIZ)
import app as A
from motor import pagamentos as PG
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

CK = []
PG.checkout_cartao = lambda dados, n, v, urls, ref, ciclo="mensal": (CK.append((n, v, ciclo)), {"id": f"ck{len(CK)}", "url": "https://x/ck"})[1]
PG.buscar_cep = lambda cep: {"rua": "R", "bairro": "B", "cidade": "C", "uf": "SP", "ibge": "3549805"}
PG.cancelar_assinatura = lambda s: None
PG.atualizar_cliente = lambda cid, tel, end: None
DADOS = {"forma": "cartao", "cpf_cnpj": "52998224725", "telefone": "17991234567", "cep": "15015000", "rua": "R", "numero": "1", "bairro": "B"}
banco = lambda: sqlite3.connect(os.environ["DADOS_DIR"] + "/estudio.sqlite3")
dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})

def cliente(email):
    tok = dono.post("/api/admin/usuarios", json={"nome": email, "email": email, "dias_acesso": 7}).json["link_convite"].split("/convite/")[1]
    c = A.app.test_client(); c.post(f"/api/convite/{tok}", json={"senha": "senha12345"})
    uid = A.buscar_usuario(email=email)["id"]
    with banco() as b: b.execute("UPDATE usuarios SET asaas_customer_id=? WHERE id=?", ("cus_" + uid, uid))
    return c, uid

def pagar(uid, valor, evt):
    return A.app.test_client().post("/webhooks/asaas", headers={"asaas-access-token": TOKEN}, json={
        "id": evt, "event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_" + evt, "customer": "cus_" + uid, "subscription": "sub_" + evt,
        "value": valor, "dueDate": datetime.now().strftime("%Y-%m-%d")}})

ana, ua = cliente("ana@x.com")
a = ana.get("/api/assinatura").json
pl = {p["id"]: p for p in a["planos"]}
ok(pl["essencial"]["mensal"] == 97 and pl["completo"]["mensal"] == 147 and pl["essencial"]["fundador"], "com vagas: preço de fundador (97 / 147)")
ok(pl["essencial"]["cheio_mensal"] == 147 and pl["completo"]["cheio_mensal"] == 197, "mostra o preço cheio pra riscar")
ok(pl["essencial"]["anual"] == 970 and pl["completo"]["anual"] == 1470 and a["meses_anual"] == 10, "anual = 10 meses (2 grátis)")
ok(a["vagas_fundador"] == 2, "conta as vagas de fundador")

# Ana: Completo anual, preço de fundador
ok(ana.post("/api/assinatura/iniciar", json={"plano": "completo", "ciclo": "trimestral", **DADOS}).status_code == 400, "recusa período inválido")
ana.post("/api/assinatura/iniciar", json={"plano": "completo", "ciclo": "anual", **DADOS})
ok(CK[-1] == ("Advoga+ Completo (anual)", 1470.0, "anual") or CK[-1][1:] == (1470.0, "anual"), "checkout anual de R$ 1.470 (ciclo anual no Asaas)")
pagar(ua, 1470.0, "a1")
u = A.buscar_usuario(usuario_id=ua)
ok(u["plano"] == "completo" and u["ciclo"] == "anual" and u["fundador"] == 1 and u["valor_assinatura"] == 1470.0, "vira Completo anual, fundador, valor travado registrado")
ok(datetime.fromisoformat(u["acesso_ate"]) > datetime.now() + timedelta(days=360), "anual libera ~12 meses de acesso")
ok(ana.get("/api/assinatura").json["vagas_fundador"] == 1, "uma vaga de fundador a menos")

# Beto: Essencial mensal, última vaga
beto, ub = cliente("beto@x.com")
beto.post("/api/assinatura/iniciar", json={"plano": "essencial", "ciclo": "mensal", **DADOS})
ok(CK[-1][1:] == (97.0, "mensal"), "checkout mensal de R$ 97 (fundador)")
pagar(ub, 97.0, "b1")
u = A.buscar_usuario(usuario_id=ub)
ok(u["fundador"] == 1 and u["ciclo"] == "mensal" and datetime.fromisoformat(u["acesso_ate"]) < datetime.now() + timedelta(days=40), "Beto fundador mensal, ~1 mês")

# Carla: vagas acabaram -> preço cheio
carla, uc = cliente("carla@x.com")
a = carla.get("/api/assinatura").json
pl = {p["id"]: p for p in a["planos"]}
ok(a["vagas_fundador"] == 0 and pl["essencial"]["mensal"] == 147 and not pl["essencial"]["fundador"], "vagas esgotadas: passa sozinho pro preço cheio")
carla.post("/api/assinatura/iniciar", json={"plano": "essencial", "ciclo": "mensal", **DADOS})
ok(CK[-1][1:] == (147.0, "mensal"), "checkout no preço cheio")
pagar(uc, 147.0, "c1")
ok(A.buscar_usuario(usuario_id=uc)["fundador"] == 0, "Carla não é fundadora")

# Beto renova depois das vagas acabarem: continua fundador (preço travado)
pagar(ub, 97.0, "b2")
u = A.buscar_usuario(usuario_id=ub)
ok(u["fundador"] == 1 and u["valor_assinatura"] == 97.0, "renovação do fundador mantém o preço travado")
painel = {x["email"]: x for x in dono.get("/api/admin/usuarios").json["usuarios"]}
ok(painel["ana@x.com"]["ciclo"] == "anual" and painel["ana@x.com"]["fundador"] and not painel["carla@x.com"]["fundador"], "painel mostra anual e fundador")

# prazo do fundador
ok(ana.get("/api/assinatura").json["vagas_fundador_total"] == 2, "informa o total de vagas (pra mostrar 'X de Y preenchidas')")
A.FUNDADOR_ATE = "2020-01-01"
dani, ud = cliente("dani@x.com")
with banco() as b: b.execute("UPDATE usuarios SET fundador=0")  # libera vagas, mas o prazo já passou
a = dani.get("/api/assinatura").json
ok(a["vagas_fundador"] == 0 and a["fundador_ate"] is None and {p["id"]: p for p in a["planos"]}["essencial"]["mensal"] == 147,
   "prazo vencido: preço cheio mesmo com vagas sobrando")
A.FUNDADOR_ATE = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
a = dani.get("/api/assinatura").json
ok(a["vagas_fundador"] == 2 and a["fundador_ate"] == A.FUNDADOR_ATE and {p["id"]: p for p in a["planos"]}["essencial"]["mensal"] == 97,
   "dentro do prazo: preço de fundador e data informada pra tela")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
