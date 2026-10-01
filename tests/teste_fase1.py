"""
Testes da Fase 1: e-mails automáticos (convite, boas-vindas, primeiro post,
teste acabando, teste encerrado, cada um uma vez só), trocar senha, excluir
conta (cancela a cobrança), remoção pelo dono e sugestões de tema.
Rodar: python tests/teste_fase1.py
"""
import os, sys, json, time, types, tempfile, sqlite3
from datetime import datetime, timedelta
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_f1_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="f"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", DONO_NOME="Felipe",
                  RESEND_API_KEY="re_teste", EMAIL_REMETENTE="Felipe <felipe@x.com>", APP_URL="https://posts.exemplo.com",
                  EMAILS_AUTOMATICOS="0", ASAAS_API_KEY="$aact_t", SUPORTE_WHATSAPP="+55 (17) 99999-0000", LIMITE_SUGESTOES_DIA="1")
sys.path.insert(0, RAIZ)
import app as A
from motor import emails as E, gerar_post as G, pagamentos as PG, publicador as PU
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

ENVIADOS = []
E.enviar = lambda para, assunto, h, t: (ENVIADOS.append((para, assunto, h, t)), True)[1]
CANCELADAS = []
PG.cancelar_assinatura = lambda s: CANCELADAS.append(s)
PU.desconectar = lambda a: None
CHAMADAS_IA = []
class B:
    def __init__(s, t): s.type = "text"; s.text = t
class M:
    falhar = False
    def create(s, **kw):
        CHAMADAS_IA.append(kw["system"][:40])
        if M.falhar: raise RuntimeError("fora do ar")
        if "Você sugere temas" in kw["system"]:
            out = {"sugestoes": [{"tema": "Golpe do falso suporte — como evitar.", "frente": "Golpes"}, {"tema": "Ative os dois fatores", "frente": "Inexistente"}]}
        else:
            out = {"titulo_interno": "T", "slides": ["a"], "legenda": "l", "hashtags": [], "alertas": []}
        return types.SimpleNamespace(content=[B(json.dumps(out, ensure_ascii=False))], usage=types.SimpleNamespace(input_tokens=10, output_tokens=10, server_tool_use=None))
G._cliente = lambda: types.SimpleNamespace(messages=M())
banco = lambda: sqlite3.connect(os.environ["DADOS_DIR"] + "/estudio.sqlite3")
para = lambda email: [e for e in ENVIADOS if e[0] == email]

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
ok(dono.get("/api/eu").json["suporte"]["whatsapp"] == "5517999990000" and dono.get("/api/eu").json["emails_configurados"], "suporte e e-mails no /api/eu")

# --- convite e boas-vindas ---
r = dono.post("/api/admin/usuarios", json={"nome": "Ana Souza", "email": "ana@x.com", "dias_acesso": 7, "enviar_email": True})
ok(r.json["email_enviado"] is True and "Criar minha senha" in para("ana@x.com")[0][2] and "/convite/" in para("ana@x.com")[0][3], "convite por e-mail com o link")
dono.post("/api/admin/usuarios", json={"nome": "Beto", "email": "beto@x.com", "dias_acesso": 7})
ok(not para("beto@x.com"), "sem marcar a opção, não manda convite por e-mail")
tok = r.json["link_convite"].split("/convite/")[1]
ana = A.app.test_client(); ana.post(f"/api/convite/{tok}", json={"senha": "senha12345"}); time.sleep(0.5)
bv = [e for e in para("ana@x.com") if "Bem-vindo" in e[1]]
ok(len(bv) == 1 and "DNA de escrita" in bv[0][2] and "https://posts.exemplo.com" in bv[0][3] and "wa.me/5517999990000" in bv[0][2], "boas-vindas ao criar a senha (passos, dica do DNA, link e WhatsApp)")
uid = A.buscar_usuario(email="ana@x.com")["id"]
ok(A.buscar_usuario(usuario_id=uid)["ativado_em"], "guarda a data de ativação")

# --- rotina ---
ok(A.rodar_rotina_emails() == [], "logo após ativar: nenhum lembrete")
with banco() as c: c.execute("UPDATE usuarios SET ativado_em=? WHERE id=?", ((datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds"), uid))
ok(A.rodar_rotina_emails() == [("lembrete_primeiro_post", "ana@x.com")], "30h sem post: lembrete do primeiro post")
ok(A.rodar_rotina_emails() == [], "lembrete não repete")
with banco() as c: c.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", ((datetime.now() + timedelta(days=1, hours=5)).isoformat(timespec="seconds"), uid))
env = A.rodar_rotina_emails()
ok(env == [("teste_acabando", "ana@x.com")] and "fundador" in para("ana@x.com")[-1][3].lower(), "faltando ~2 dias: teste acabando (com a oferta)")
with banco() as c: c.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", ((datetime.now() - timedelta(hours=5)).isoformat(timespec="seconds"), uid))
ok(A.rodar_rotina_emails() == [("teste_encerrado", "ana@x.com")], "teste vencido: teste encerrado")
ok(A.rodar_rotina_emails() == [], "nenhum e-mail se repete")
with banco() as c: c.execute("UPDATE usuarios SET pagante=1, acesso_ate=?, ativado_em=? WHERE email='beto@x.com'",
                             ((datetime.now() + timedelta(days=1)).isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")))
with banco() as c: c.execute("UPDATE usuarios SET status='ativo' WHERE email='beto@x.com'")
ok(all(e[1] != "beto@x.com" for e in A.rodar_rotina_emails()), "pagante não recebe 'teste acabando'")

# --- trocar senha ---
ok(ana.post("/api/conta/senha", json={"atual": "errada", "nova": "novasenha123"}).status_code == 400, "trocar senha: senha atual errada é recusada")
ok(ana.post("/api/conta/senha", json={"atual": "senha12345", "nova": "curta"}).status_code == 400, "trocar senha: exige 8 caracteres")
ok(ana.post("/api/conta/senha", json={"atual": "senha12345", "nova": "novasenha123"}).status_code == 200, "trocar senha: ok")
ok(A.app.test_client().post("/api/login", json={"email": "ana@x.com", "senha": "novasenha123"}).status_code == 200, "entra com a senha nova")

# --- sugestões de tema ---
with banco() as c: c.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", ((datetime.now() + timedelta(days=5)).isoformat(timespec="seconds"), uid))
pid = ana.post("/api/perfis", json={"nome_exibicao": "Ana", "modelo": "digital_consumidor"}).json["id"]
p = [x for x in ana.get("/api/perfis").json if x["id"] == pid][0]; p["frentes"] = [{"nome": "Golpes", "descricao": "Pix, falso atendente, links falsos"}, {"nome": "Contas", "descricao": "Hackeadas, banidas"}]
ana.put(f"/api/perfis/{pid}", json=p)
n0 = len(CHAMADAS_IA); s1 = ana.get(f"/api/perfis/{pid}/sugestoes").json["sugestoes"]
ok(s1[0] == {"tema": "Golpe do falso suporte, como evitar", "frente": "Golpes"} and s1[1]["frente"] == "Golpes", "sugestões limpas (sem travessão/ponto) e frente válida")
ana.get(f"/api/perfis/{pid}/sugestoes")
ok(len(CHAMADAS_IA) == n0 + 1, "sugestões ficam guardadas (não gasta IA de novo)")
ana.get(f"/api/perfis/{pid}/sugestoes?novas=1")
r = ana.get(f"/api/perfis/{pid}/sugestoes?novas=1").json
ok(r.get("aviso") and len(CHAMADAS_IA) == n0 + 2, "'Outras ideias' tem limite diário pro convidado")
M.falhar = True
with banco() as c: c.execute("UPDATE perfis SET sugestoes=NULL WHERE id=?", (pid,))
r = dono.get(f"/api/perfis/{pid}/sugestoes?novas=1").json["sugestoes"]
ok(r and r[0]["tema"] == "Pix" and r[0]["frente"] == "Golpes", "IA fora do ar: sugestões a partir dos temas do perfil")
M.falhar = False
ok(A.app.test_client().get(f"/api/perfis/{pid}/sugestoes").status_code == 401, "sugestões exigem login")

# --- excluir conta ---
with banco() as c: c.execute("UPDATE usuarios SET asaas_subscription_id='sub_ana' WHERE id=?", (uid,))
ok(ana.post("/api/conta/excluir", json={"senha": "errada"}).status_code == 400, "excluir conta: senha errada é recusada")
ok(ana.post("/api/conta/excluir", json={"senha": "novasenha123"}).status_code == 200, "excluir conta: ok")
ok("sub_ana" in CANCELADAS and A.buscar_usuario(usuario_id=uid) is None and A.buscar_perfil(pid) is None, "excluir conta cancela a assinatura e apaga tudo")
ok(dono.post("/api/conta/excluir", json={"senha": "senhadodono123"}).status_code == 400, "dono não exclui a própria conta por aqui")

# --- remoção pelo dono cancela a cobrança ---
ub = A.buscar_usuario(email="beto@x.com")
with banco() as c: c.execute("UPDATE usuarios SET asaas_subscription_id='sub_beto' WHERE id=?", (ub["id"],))
dono.delete(f"/api/admin/usuarios/{ub['id']}")
ok("sub_beto" in CANCELADAS and A.buscar_usuario(usuario_id=ub["id"]) is None, "dono remove pessoa: cancela a assinatura no Asaas")

# --- sem e-mail configurado ---
os.environ["RESEND_API_KEY"] = ""
n = len(ENVIADOS); dono.post("/api/admin/usuarios", json={"nome": "Caio", "email": "caio@x.com", "dias_acesso": 7, "enviar_email": True})
ok(len(ENVIADOS) == n and A.rodar_rotina_emails() == [], "sem Resend configurado: não envia nada (e nada quebra)")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
