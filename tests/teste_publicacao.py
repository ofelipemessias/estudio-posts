"""
Testes da publicação automática (Zernio simulado): upgrade por pessoa,
conexão do Instagram (com conferência na API), publicar agora, agendar,
agenda, cancelamento e desconexão quando o upgrade é desligado.
Rodar: python tests/teste_publicacao.py
"""
import os, sys, json, types, time, tempfile
from datetime import datetime, timedelta, timezone
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_pub_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="z"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", ZERNIO_API_KEY="sk_teste")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g, publicador as P
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)

# ---- IA simulada ----
class B:
    def __init__(s, t): s.type = "text"; s.text = t
class M:
    def create(s, **kw):
        out = {"titulo_interno": "T", "slides": ["a", "b", "c"], "legenda": "Legenda", "hashtags": ["#x"], "alertas": []}
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, server_tool_use=None))
g._cliente = lambda: types.SimpleNamespace(messages=M())

# ---- Zernio simulado ----
Z = {"perfis": {}, "contas": {}, "posts": {}, "desconectadas": [], "uploads": 0, "cancelados": []}
def criar_perfil(nome): pid = f"zp{len(Z['perfis'])+1}"; Z["perfis"][pid] = nome; return pid
def link_conexao(pid, volta): Z["ultimo_retorno"] = volta; return "https://instagram.example/oauth?x=1"
def contas_instagram(pid): return Z["contas"].get(pid, [])
def desconectar(acc): Z["desconectadas"].append(acc)
def enviar_imagem(conteudo, nome, tipo="image/png"): Z["uploads"] += 1; return f"https://media.zernio.com/{nome}"
def criar_post(acc, legenda, urls, quando, id_requisicao=None):
    zid = f"zpost{len(Z['posts'])+1}"; Z["posts"][zid] = {"acc": acc, "legenda": legenda, "urls": urls, "quando": quando}
    return {"id": zid, "status": "agendado" if quando else "publicando", "url": None, "erro": None}
def ver_post(zid): return {"id": zid, "status": "publicado", "url": f"https://instagram.com/p/{zid}", "erro": None}
def cancelar_post(zid): Z["cancelados"].append(zid)
for nome, f in dict(criar_perfil=criar_perfil, link_conexao=link_conexao, contas_instagram=contas_instagram, desconectar=desconectar,
                    enviar_imagem=enviar_imagem, criar_post=criar_post, ver_post=ver_post, cancelar_post=cancelar_post).items():
    setattr(P, nome, f)

dono = A.app.test_client(); dono.post("/api/login", json={"email": "dono@teste.com", "senha": "senhadodono123"})
tok = dono.post("/api/admin/usuarios", json={"nome": "Ana", "email": "ana@x.com", "dias_acesso": 30}).json["link_convite"].split("/convite/")[1]
ana = A.app.test_client(); ana.post(f"/api/convite/{tok}", json={"senha": "senha12345"})
tok2 = dono.post("/api/admin/usuarios", json={"nome": "Beto", "email": "beto@x.com", "dias_acesso": 30}).json["link_convite"].split("/convite/")[1]
beto = A.app.test_client(); beto.post(f"/api/convite/{tok2}", json={"senha": "senha12345"})
pa = ana.post("/api/perfis", json={"nome_exibicao": "Dra. Ana", "modelo": "previdenciario"}).json["id"]
pb = beto.post("/api/perfis", json={"nome_exibicao": "Dr. Beto", "modelo": "trabalhista"}).json["id"]
post = ana.post(f"/api/perfis/{pa}/posts", json={"formato": "carrossel", "tema": "x"}).json["id"]; time.sleep(1.5)

eu = ana.get("/api/eu").json["publicacao"]
ok(eu == {"configurada": True, "liberada": False}, "convidado começa SEM a publicação automática")
r = ana.post(f"/api/perfis/{pa}/instagram/conectar")
ok(r.status_code == 403 and r.json["codigo"] == "sem_upgrade", "sem upgrade: não conecta Instagram")
ok(ana.post(f"/api/posts/{post}/publicar", json={}).status_code == 403, "sem upgrade: não publica")

uid_ana = [u for u in dono.get("/api/admin/usuarios").json["usuarios"] if u["email"] == "ana@x.com"][0]["id"]
dono.put(f"/api/admin/usuarios/{uid_ana}", json={"acao": "publicacao", "ativo": True})
ok(ana.get("/api/eu").json["publicacao"]["liberada"], "dono liberou o upgrade da Ana")
ok(ana.post(f"/api/posts/{post}/publicar", json={}).status_code == 400, "sem Instagram conectado: pede pra conectar")

r = ana.post(f"/api/perfis/{pa}/instagram/conectar")
ok(r.status_code == 200 and r.json["url"].startswith("https://instagram.example"), "gera o link de login do Instagram")
zp = A.buscar_perfil(pa)["zernio_profile_id"]
ok(zp == "zp1" and "perfil=" + pa in Z["ultimo_retorno"], "cria perfil no Zernio e define a volta pro sistema")
ok(beto.post(f"/api/perfis/{pa}/instagram/conectar").status_code == 404, "Beto não conecta Instagram no perfil da Ana")

# retorno forjado: conta que NÃO existe no Zernio
r = ana.get(f"/instagram/conectado?perfil={pa}&accountId=conta_falsa")
ok(r.status_code == 302 and "instagram=erro" in r.headers["Location"] and not A.buscar_perfil(pa)["ig_account_id"],
   "retorno com conta inexistente é recusado (conferido na API)")
Z["contas"][zp] = [{"_id": "acc_ana", "username": "anasouzaadv", "platform": "instagram"}]
r = ana.get(f"/instagram/conectado?perfil={pa}&accountId=acc_ana")
p = A.buscar_perfil(pa)
ok("instagram=conectado" in r.headers["Location"] and p["ig_account_id"] == "acc_ana" and p["ig_username"] == "anasouzaadv",
   "conta confirmada na API é salva no perfil")
ok(A.app.test_client().get(f"/instagram/conectado?perfil={pa}&accountId=acc_ana").headers["Location"] == "/", "retorno sem login não faz nada")
lista = ana.get("/api/perfis").json[0]
ok(lista["ig_username"] == "anasouzaadv" and "ig_account_id" not in lista, "tela recebe o @, mas não os ids internos")

# publicar agora
r = ana.post(f"/api/posts/{post}/publicar", json={}); time.sleep(0.8)
ag = ana.get(f"/api/perfis/{pa}/agenda").json
ok(r.status_code == 202 and len(ag) == 1 and ag[0]["status"] in ("publicando", "publicado"), "publicar agora entra na agenda")
zpost = Z["posts"]["zpost1"]
ok(Z["uploads"] == 3 and len(zpost["urls"]) == 3 and zpost["quando"] is None and "#x" in zpost["legenda"], "sobe as 3 artes e manda legenda + hashtags")

# agendar
br = timezone(timedelta(hours=-3))
ok(ana.post(f"/api/posts/{post}/publicar", json={"quando": (datetime.now(br) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M")}).status_code == 400,
   "recusa horário a menos de 5 minutos")
ok(ana.post(f"/api/posts/{post}/publicar", json={"quando": "amanha"}).status_code == 400, "recusa data inválida")
quando = (datetime.now(br) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
r = ana.post(f"/api/posts/{post}/publicar", json={"quando": quando}); time.sleep(0.8)
ag2 = [a for a in ana.get(f"/api/perfis/{pa}/agenda").json if a["id"] == r.json["id"]][0]
ok(ag2["status"] == "agendado" and ag2["quando"] == quando and Z["posts"]["zpost2"]["quando"] == quando, "agendamento com data e hora")
ok(beto.get(f"/api/perfis/{pa}/agenda").status_code == 404, "Beto não vê a agenda da Ana")
ok(beto.delete(f"/api/agendamentos/{ag2['id']}").status_code == 404, "Beto não cancela agendamento da Ana")
ok(ana.delete(f"/api/agendamentos/{ag2['id']}").status_code == 200 and "zpost2" in Z["cancelados"], "Ana cancela o agendamento")

# reels não publica
reel = ana.post(f"/api/perfis/{pa}/posts", json={"formato": "reels", "tema": "y"}).json["id"]; time.sleep(1.2)
ok(ana.post(f"/api/posts/{reel}/publicar", json={}).status_code == 400, "Reels: explica que precisa de vídeo")

# desligar upgrade desconecta
dono.put(f"/api/admin/usuarios/{uid_ana}", json={"acao": "publicacao", "ativo": False})
ok("acc_ana" in Z["desconectadas"] and not A.buscar_perfil(pa)["ig_account_id"], "desligar o upgrade desconecta o Instagram (para de pagar)")
ok(dono.get("/api/admin/usuarios").json["usuarios"][1]["publicacao_auto"] in (False, True), "painel mostra a situação do upgrade")

# dono sempre pode; apagar perfil desconecta
pd = dono.post("/api/perfis", json={"nome_exibicao": "Grupo", "modelo": "digital_consumidor"}).json["id"]
dono.post(f"/api/perfis/{pd}/instagram/conectar"); zpd = A.buscar_perfil(pd)["zernio_profile_id"]
Z["contas"][zpd] = [{"_id": "acc_gm", "username": "grupomello"}]
dono.get(f"/instagram/conectado?perfil={pd}&accountId=acc_gm")
ok(A.buscar_perfil(pd)["ig_username"] == "grupomello", "dono conecta sem precisar de upgrade")
dono.delete(f"/api/perfis/{pd}")
ok("acc_gm" in Z["desconectadas"], "apagar perfil desconecta o Instagram dele")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
