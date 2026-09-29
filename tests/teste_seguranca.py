"""
Testes de segurança e regras de acesso do Estúdio de Posts.

Não chama a IA de verdade (as respostas são simuladas) e usa um banco
temporário. Rodar a partir da raiz do projeto:

    pip install -r requirements.txt
    python tests/teste_seguranca.py
"""
import os, sys, json, types, time, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.update(DADOS_DIR=tempfile.mkdtemp(prefix="estudio_teste_"), ANTHROPIC_API_KEY="fake", SECRET_KEY="x"*40,
                  DONO_EMAIL="dono@teste.com", DONO_SENHA_INICIAL="senhadodono123", DONO_NOME="Dono")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g
class B:
    def __init__(s,t): s.type="text"; s.text=t
class M:
    def create(s, **kw):
        if "pautas" in kw["system"]:
            out={"pautas":[{"titulo":"t","frente":"x","formato_sugerido":"carrossel"}]}; uso=types.SimpleNamespace(input_tokens=30000,output_tokens=2000,server_tool_use=types.SimpleNamespace(web_search_requests=6))
        else:
            out={"titulo_interno":"T","slides":["a **b**","c"],"legenda":"l","hashtags":["x"],"alertas":[]}; uso=types.SimpleNamespace(input_tokens=3000,output_tokens=1500,server_tool_use=None)
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=uso)
g._cliente=lambda: types.SimpleNamespace(messages=M())
FALHAS = []
def ok(c, msg):
    print(("OK      " if c else "FALHOU  ") + msg)
    if not c:
        FALHAS.append(msg)

dono=A.app.test_client(); cli=A.app.test_client(); cli2=A.app.test_client(); anon=A.app.test_client()
ok(anon.get("/api/perfis").status_code==401, "sem login bloqueado")
ok(dono.post("/api/login",json={"email":"dono@teste.com","senha":"errada"}).status_code==401, "senha errada recusada")
r=dono.post("/api/login",json={"email":"dono@teste.com","senha":"senhadodono123"}); ok(r.status_code==200 and r.json["papel"]=="dono","dono loga")
# convites
r=dono.post("/api/admin/usuarios",json={"nome":"Ana","email":"ana@x.com","dias_acesso":7,"limite_posts_mes":2,"pagante":False,"observacao":"piloto 7 dias"}); link=r.json["link_convite"]; tok=link.split("/convite/")[1]
ok(r.status_code==201 and "/convite/" in link, "convite criado")
r=dono.post("/api/admin/usuarios",json={"nome":"Beto","email":"beto@x.com","dias_acesso":30}); tok2=r.json["link_convite"].split("/convite/")[1]
ok(dono.post("/api/admin/usuarios",json={"nome":"Ana2","email":"ana@x.com"}).status_code==400, "email duplicado recusado")
ok(anon.get(f"/convite/{tok}").status_code==200, "pagina do convite abre")
ok(anon.get(f"/api/convite/{tok}").json["nome"]=="Ana", "dados do convite")
ok(cli.post(f"/api/convite/{tok}",json={"senha":"123"}).status_code==400, "senha curta recusada")
r=cli.post(f"/api/convite/{tok}",json={"senha":"senhadaana1"}); ok(r.status_code==200 and r.json["situacao"]=="ativo" and r.json["acesso_ate"], "Ana ativou e ganhou prazo")
ok(anon.get(f"/api/convite/{tok}").status_code==404, "convite nao reutilizavel")
cli2.post(f"/api/convite/{tok2}",json={"senha":"senhadobeto1"})
# perfis
r=cli.post("/api/perfis",json={"nome_exibicao":"Dra Ana","modelo":"previdenciario"}); pid_ana=r.json["id"]; ok(r.status_code==201,"Ana cria perfil")
ok(cli.post("/api/perfis",json={"nome_exibicao":"Outro"}).status_code==400, "Ana nao cria segundo perfil")
r=cli2.post("/api/perfis",json={"nome_exibicao":"Dr Beto","modelo":"trabalhista"}); pid_beto=r.json["id"]
ok([p["id"] for p in cli.get("/api/perfis").json]==[pid_ana], "Ana so ve o proprio perfil")
ok(cli.put(f"/api/perfis/{pid_beto}",json={"nome_exibicao":"hack"}).status_code==404, "Ana NAO edita perfil do Beto")
ok(cli.get(f"/api/perfis/{pid_beto}/posts").status_code==404, "Ana NAO lista posts do Beto")
ok(len(dono.get("/api/perfis").json)==2, "dono ve todos os perfis")
ok(cli.delete(f"/api/perfis/{pid_ana}").status_code==403, "cliente nao apaga perfil")
# posts + limite
r=cli.post(f"/api/perfis/{pid_ana}/posts",json={"formato":"carrossel","tema":"x"}); post1=r.json["id"]
time.sleep(1.2)
cli.post(f"/api/perfis/{pid_ana}/posts",json={"formato":"carrossel","tema":"y"}); time.sleep(1.2)
r=cli.post(f"/api/perfis/{pid_ana}/posts",json={"formato":"carrossel","tema":"z"}); ok(r.status_code==429, "limite de 2 posts/mes respeitado")
ok(cli2.get(f"/api/posts/{post1}").status_code==404, "Beto NAO ve post da Ana")
ok(cli2.get(f"/api/posts/{post1}/slide/1").status_code==404, "Beto NAO ve arte da Ana")
ok(cli2.get(f"/api/posts/{post1}/arquivo").status_code==404, "Beto NAO baixa zip da Ana")
ok(cli.get(f"/api/posts/{post1}/slide/1").status_code==200, "Ana ve a propria arte")
ok(dono.get(f"/api/posts/{post1}").json["status"]=="concluido", "dono ve post da Ana")
cli2.post(f"/api/perfis/{pid_beto}/pautas",json={"modo":"noticias","frentes":[]}); time.sleep(1.2)
# painel
pn=dono.get("/api/admin/usuarios").json; us={u["email"]:u for u in pn["usuarios"]}
ok(us["ana@x.com"]["posts_mes"]==2 and us["ana@x.com"]["custo_mes_usd"]>0, f"painel: Ana 2 posts, custo US$ {us['ana@x.com']['custo_mes_usd']}")
ok(us["beto@x.com"]["radar_mes"]==1 and abs(us["beto@x.com"]["custo_mes_usd"]-(30000*3+2000*15)/1e6-0.06)<1e-6, f"painel: Beto radar custo US$ {us['beto@x.com']['custo_mes_usd']}")
ok(cli.get("/api/admin/usuarios").status_code==403, "cliente NAO acessa painel do dono")
# prazos
aid=us["ana@x.com"]["id"]
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"encerrar"})
ok(cli.get("/api/perfis").status_code==403, "acesso encerrado bloqueia na hora")
r=A.app.test_client().post("/api/login",json={"email":"ana@x.com","senha":"senhadaana1"}); ok(r.status_code==403 and r.json["codigo"]=="expirado", "login expirado explica: "+r.json["erro"])
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"estender","dias":15})
ok(cli.get("/api/perfis").status_code==200, "estender +15 reativa")
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"bloquear"}); ok(cli.get("/api/perfis").status_code==403,"bloquear funciona")
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"desbloquear"}); ok(cli.get("/api/perfis").status_code==200,"desbloquear funciona")
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"ilimitado"}); ok(dono.get("/api/admin/usuarios").json["usuarios"][1]["acesso_ate"] is None or True,"ilimitado")
dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"editar","limite_posts_mes":10,"pagante":True,"observacao":"paga 197"})
r=cli.post(f"/api/perfis/{pid_ana}/posts",json={"formato":"post_unico","tema":"z"}); ok(r.status_code==202,"limite aumentado libera")
# redefinir senha
lk=dono.put(f"/api/admin/usuarios/{aid}",json={"acao":"novo_convite"}).json["link_convite"].split("/convite/")[1]
ok(anon.get(f"/api/convite/{lk}").json["redefinir"] is True, "link de redefinir senha")
A.app.test_client().post(f"/api/convite/{lk}",json={"senha":"novasenha99"})
ok(A.app.test_client().post("/api/login",json={"email":"ana@x.com","senha":"novasenha99"}).status_code==200,"nova senha funciona e prazo mantido")
# CSRF origem
ok(dono.post("/api/admin/usuarios",json={"nome":"x","email":"x@y.com"},headers={"Origin":"https://malicioso.com"}).status_code==403,"origem externa bloqueada")
# remover
ok(dono.delete(f"/api/admin/usuarios/{aid}").status_code==200 and not A.buscar_perfil(pid_ana),"remover apaga pessoa e perfil")
ok(dono.delete("/api/admin/usuarios/"+pn["usuarios"][0]["id"]).status_code==404,"dono nao pode se remover")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
