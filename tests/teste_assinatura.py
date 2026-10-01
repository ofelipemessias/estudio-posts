"""
Testes da assinatura (Asaas simulado): fim do teste, tela de assinar,
checkout no cartão e Pix, webhook (senha, repetição, pagamento, atraso,
estorno, cancelamento, troca de plano) e liberação do plano Completo.
Rodar: python tests/teste_assinatura.py
"""
import os, sys, json, tempfile, sqlite3
from datetime import datetime, timedelta
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "t" * 40
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_ass_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="w"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", ASAAS_API_KEY="$aact_teste",
                  ASAAS_WEBHOOK_TOKEN=TOKEN, PRECO_ESSENCIAL="197", PRECO_COMPLETO="247", ZERNIO_API_KEY="sk_x")
sys.path.insert(0, RAIZ)
import app as A
from motor import pagamentos as PG, publicador as PU
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

CHAMADAS = {"clientes": [], "checkouts": [], "pix": [], "cancelados": []}
PG.criar_cliente = lambda nome, email, doc, ref, tel, end: (CHAMADAS["clientes"].append((nome, email, doc, ref, tel, end)), "cus_ana")[1]
PG.atualizar_cliente = lambda cid, tel, end: CHAMADAS.setdefault("atualizados", []).append((cid, tel, end))
PG.buscar_cep = lambda cep: {"rua": "Av. Teste", "bairro": "Centro", "cidade": "São José do Rio Preto", "uf": "SP", "ibge": "3549805"} if str(cep).startswith("15") else None
END = {"cep": "15015000", "numero": "100", "rua": "Av. Teste", "bairro": "Centro", "complemento": "Sala 2"}
PG.checkout_cartao = lambda dados, n, v, urls, ref: (CHAMADAS["checkouts"].append((dados, n, v, urls, ref)), {"id": "ck1", "url": "https://sandbox.asaas.com/checkoutSession/show?id=ck1"})[1]
CLIENTES_ASAAS = {"cus_ana": {"email": "ana@x.com", "cpfCnpj": "52998224725", "postalCode": "15015000", "address": "Av. Teste",
                  "addressNumber": "100", "province": "Centro", "mobilePhone": "17991234567"},
                  "cus_checkout_ana": {"email": "ANA@x.com"}, "cus_estranho": {"email": "outra@pessoa.com"}}
PG.ver_cliente = lambda cid: CLIENTES_ASAAS.get(cid, {})
PG.assinatura_pix = lambda c, n, v, ref: (CHAMADAS["pix"].append((c, n, v)), {"id": "sub_pix", "url": "https://sandbox.asaas.com/i/123"})[1]
PG.cancelar_assinatura = lambda sid: CHAMADAS["cancelados"].append(sid)
PU.desconectar = lambda a: None

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
tok = dono.post("/api/admin/usuarios", json={"nome": "Ana", "email": "ana@x.com", "dias_acesso": 7}).json["link_convite"].split("/convite/")[1]
ana = A.app.test_client(); ana.post(f"/api/convite/{tok}", json={"senha": "senha12345"})
uid = [u for u in dono.get("/api/admin/usuarios").json["usuarios"] if u["email"] == "ana@x.com"][0]["id"]
banco = lambda: sqlite3.connect(os.environ["DADOS_DIR"] + "/estudio.sqlite3")
def vencer(dias=1):
    with banco() as c: c.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", ((datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds"), uid))
def usuario(): return A.buscar_usuario(usuario_id=uid)
def webhook(evento, token=TOKEN):
    return A.app.test_client().post("/webhooks/asaas", json=evento, headers={"asaas-access-token": token})

# --- fim do teste ---
vencer()
ok(ana.get("/api/perfis").status_code == 403, "teste vencido: não usa o sistema")
r = A.app.test_client().post("/api/login", json={"email": "ana@x.com", "senha": "senha12345"})
ok(r.status_code == 200 and r.json["situacao"] == "expirado", "teste vencido: consegue entrar (pra assinar)")
ok(ana.get("/api/eu").json["situacao"] == "expirado", "tela sabe que o teste venceu")
a = ana.get("/api/assinatura").json
ok(a["configurada"] and [p["valor"] for p in a["planos"]] == [197.0, 247.0], "planos e preços vêm do .env")

# --- assinar no cartão ---
ok(ana.post("/api/assinatura/iniciar", json={"plano": "completo", "forma": "cartao", "cpf_cnpj": "52998224725", **END}).status_code == 400, "exige celular (o checkout do Asaas pede telefone)")
ok(ana.post("/api/assinatura/iniciar", json={"plano": "completo", "forma": "cartao", "cpf_cnpj": "52998224725", "telefone": "17991234567", "cep": "15015000"}).status_code == 400,
   "exige endereço completo (o checkout do Asaas pede endereço)")
ok(ana.post("/api/assinatura/iniciar", json={"plano": "completo", "forma": "cartao", "cpf_cnpj": "123", "telefone": "17991234567", **END}).status_code == 400, "recusa CPF/CNPJ inválido")
ok(ana.get("/api/cep/15015000").json["cidade"] == "São José do Rio Preto" and ana.get("/api/cep/99999999").status_code == 404, "consulta de CEP")
r = ana.post("/api/assinatura/iniciar", json={"plano": "completo", "forma": "cartao", "cpf_cnpj": "529.982.247-25", "telefone": "(17) 99123-4567", **END})
ok(r.status_code == 200 and "checkoutSession" in r.json["url"], "cartão: devolve o link do checkout do Asaas")
ok(CHAMADAS["clientes"][0][2] == "52998224725" and CHAMADAS["clientes"][0][4] == "17991234567" and CHAMADAS["clientes"][0][5]["rua"] == "Av. Teste"
   and CHAMADAS["checkouts"][0][2] == 247.0, "cria cliente no Asaas (com telefone e endereço) e checkout de R$ 247")
ok(ana.get("/api/assinatura").json["cadastro_completo"], "não pede celular e endereço de novo")
d = CHAMADAS["checkouts"][0][0]
ok(d["ibge"] == "3549805" and d["email"] == "ana@x.com" and d["cpf_cnpj"] and d["numero"] == "100" and CHAMADAS["checkouts"][0][4] == uid,
   "checkout leva os dados completos do pagador (com o código IBGE da cidade)")
ok("assinatura=sucesso" in CHAMADAS["checkouts"][0][3]["sucesso"], "volta pro sistema depois de pagar")
ok(usuario()["asaas_customer_id"] == "cus_ana" and usuario()["plano_pendente"] == "completo", "guarda cliente e plano escolhido")

# --- checkout cria um cliente novo no Asaas: associa pelo e-mail ---
r = webhook({"id": "evt0a", "event": "PAYMENT_CONFIRMED", "payment": {"customer": "cus_estranho", "value": 247.0}})
ok(r.json["resultado"] == "cliente_desconhecido", "pagamento de e-mail desconhecido não libera ninguém")
with banco() as c: c.execute("UPDATE usuarios SET plano_pendente=NULL WHERE id=?", (uid,))
r = webhook({"id": "evt0b", "event": "PAYMENT_CONFIRMED", "payment": {"customer": "cus_checkout_ana", "value": 247.0}})
ok(r.json["resultado"] == "cliente_desconhecido" and not usuario()["pagante"], "sem pagamento iniciado no sistema, e-mail igual não basta")
with banco() as c: c.execute("UPDATE usuarios SET plano_pendente='completo' WHERE id=?", (uid,))

# --- webhook: segurança ---
pago = {"id": "evt1", "event": "PAYMENT_CONFIRMED", "payment": {"id": "pay1", "customer": "cus_checkout_ana", "subscription": "sub_card",
        "value": 247.0, "dueDate": datetime.now().strftime("%Y-%m-%d"), "status": "CONFIRMED"}}
ok(webhook(pago, token="errado").status_code == 401, "webhook sem a senha certa é recusado")
ok(not usuario()["pagante"], "aviso falso não libera nada")
r = webhook(pago)
u = usuario()
ok(r.status_code == 200 and r.json["resultado"] == "pago:completo", "pagamento confirmado é aplicado")
fim1 = u["acesso_ate"]
ok(u["pagante"] and u["plano"] == "completo" and u["assinatura_status"] == "ativa" and u["asaas_subscription_id"] == "sub_card", "vira pagante, plano Completo, assinatura ativa")
ok(datetime.fromisoformat(fim1) > datetime.now() + timedelta(days=33), "acesso estendido por ~1 mês (+ tolerância)")
ok(u["asaas_customer_id"] == "cus_checkout_ana", "associa o cliente criado pelo checkout à pessoa (pelo e-mail)")
ok(u["publicacao_auto"] == 1, "Completo libera a publicação automática")
ok(ana.get("/api/perfis").status_code == 200, "volta a usar o sistema")
ok(webhook(pago).json.get("repetido") and usuario()["acesso_ate"] == fim1, "aviso repetido não dá mês extra")
webhook({**pago, "id": "evt1b", "event": "PAYMENT_RECEIVED"})
ok(usuario()["acesso_ate"] == fim1, "CONFIRMED + RECEIVED do mesmo pagamento não somam 2 meses")

# --- atraso / renovação ---
webhook({"id": "evt2", "event": "PAYMENT_OVERDUE", "payment": {"customer": "cus_checkout_ana", "subscription": "sub_card"}})
ok(usuario()["assinatura_status"] == "atrasada" and ana.get("/api/perfis").status_code == 200, "atraso marca 'atrasada' mas não corta na hora")
painel = {x["email"]: x for x in dono.get("/api/admin/usuarios").json["usuarios"]}
ok(painel["ana@x.com"]["assinatura_status"] == "atrasada" and painel["ana@x.com"]["plano"] == "completo", "painel mostra plano e atraso")
prox = (datetime.fromisoformat(fim1) - timedelta(days=3)).strftime("%Y-%m-%d")
webhook({"id": "evt3", "event": "PAYMENT_RECEIVED", "payment": {"customer": "cus_checkout_ana", "subscription": "sub_card", "value": 247.0, "dueDate": prox}})
ok(datetime.fromisoformat(usuario()["acesso_ate"]) > datetime.fromisoformat(fim1) + timedelta(days=25) and usuario()["assinatura_status"] == "ativa",
   "pagamento do mês seguinte estende de novo")

# --- troca pra Essencial no Pix ---
r = ana.post("/api/assinatura/iniciar", json={"plano": "essencial", "forma": "pix"})
ok(r.status_code == 200 and CHAMADAS["pix"][-1][2] == 197.0, "Pix: assinatura de R$ 197 e link da cobrança")
webhook({"id": "evt4", "event": "PAYMENT_RECEIVED", "payment": {"customer": "cus_checkout_ana", "subscription": "sub_pix", "value": 197.0,
         "dueDate": datetime.now().strftime("%Y-%m-%d")}})
u = usuario()
ok(u["plano"] == "essencial" and u["publicacao_auto"] == 0, "trocou pro Essencial: desliga publicação automática")
ok("sub_card" in CHAMADAS["cancelados"] and u["asaas_subscription_id"] == "sub_pix", "cancela a assinatura antiga ao trocar de plano")

# --- cancelar ---
ok(ana.post("/api/assinatura/cancelar").status_code == 200 and usuario()["assinatura_status"] == "cancelada", "pessoa cancela a assinatura")
ok(ana.get("/api/perfis").status_code == 200, "cancelada: continua usando até o fim do período pago")

# --- estorno ---
webhook({"id": "evt5", "event": "PAYMENT_REFUNDED", "payment": {"customer": "cus_checkout_ana", "value": 197.0}})
ok(usuario()["assinatura_status"] == "estornada" and ana.get("/api/perfis").status_code == 403, "estorno encerra o acesso")

# --- cliente cadastrado antes, sem telefone ---
with banco() as c: c.execute("UPDATE usuarios SET asaas_cadastro_ok=NULL WHERE id=?", (uid,))
vencer()
r = ana.post("/api/assinatura/iniciar", json={"plano": "essencial", "forma": "cartao", "telefone": "17991234567", **END})
ok(r.status_code == 200 and CHAMADAS["atualizados"][-1][0] == "cus_checkout_ana" and CHAMADAS["atualizados"][-1][2]["numero"] == "100",
   "cadastro antigo incompleto: completa telefone e endereço no Asaas")

# --- outros ---
ok(webhook({"id": "evt6", "event": "PAYMENT_CONFIRMED", "payment": {"customer": "cus_outra", "value": 10}}).json["resultado"] == "cliente_desconhecido",
   "pagamento de cliente desconhecido é ignorado")
ok(dono.post("/api/assinatura/iniciar", json={"plano": "completo", "forma": "cartao"}).status_code == 400, "dono não assina")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
