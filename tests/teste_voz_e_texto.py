"""
Testes da voz dos posts, limpeza de travessões e migração de banco antigo.
Rodar a partir da raiz do projeto: python tests/teste_voz_e_texto.py
"""
import os, sys, json, types, sqlite3, tempfile
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = tempfile.mkdtemp(prefix="estudio_voz_")
# banco "antigo", sem a coluna voz (como o de quem usava a versão 0.2)
con=sqlite3.connect(D+"/estudio.sqlite3")
con.execute("CREATE TABLE perfis (id TEXT PRIMARY KEY, nome_exibicao TEXT NOT NULL, handle TEXT, area TEXT, sobre TEXT, frentes TEXT, publico TEXT, dna TEXT, estilo_visual TEXT NOT NULL DEFAULT 'escuro', cores TEXT, avatar TEXT, criado_em TEXT NOT NULL, usuario_id TEXT)")
con.execute("INSERT INTO perfis (id,nome_exibicao,frentes,criado_em) VALUES ('p1','Dra. Exemplo','[{\"nome\":\"Contas\",\"descricao\":\"x\"}]','2026-09-29T00:00:00')")
con.commit(); con.close()
os.environ.update(DADOS_DIR=D, ANTHROPIC_API_KEY="fake", SECRET_KEY="z"*40, DONO_EMAIL="f@t.com", DONO_SENHA_INICIAL="senhadodono123")
sys.path.insert(0, RAIZ)
import app as A
from motor import gerar_post as g
capt={}
class B:
    def __init__(s,t): s.type="text"; s.text=t
class M:
    def create(s, **kw):
        capt["sys"]=kw["system"]
        out={"titulo_interno":"T","slides":["Eu vejo isso — todo dia"],"legenda":"Legenda — com travessão – aqui","hashtags":["x"],"alertas":[],
             "roteiro_reels":{"gancho":"Gancho — forte","cenas":[{"tempo":"0-3s","fala":"Fala — um","na_tela":"Tela – dois"}],"fechamento":"Fim — ok"}}
        return types.SimpleNamespace(content=[B(json.dumps(out))], usage=types.SimpleNamespace(input_tokens=1,output_tokens=1,server_tool_use=None))
g._cliente=lambda: types.SimpleNamespace(messages=M())
FALHAS = []
def ok(c, m):
    print(("OK      " if c else "FALHOU  ") + m)
    if not c:
        FALHAS.append(m)
p=A.buscar_perfil("p1"); ok(p["voz"]=="neutra" and p["nome_exibicao"]=="Dra. Exemplo","banco antigo migrado: perfil mantido, voz=neutra")
c=A.app.test_client(); c.post("/api/login",json={"email":"f@t.com","senha":"senhadodono123"})
ok(A.buscar_perfil("p1")["usuario_id"] is not None,"perfil antigo ficou com o dono")
ok(len(c.get("/api/opcoes").json["vozes"])==3,"opções de voz na API")
body=dict(nome_exibicao="Dra. Exemplo",handle="@dra.exemplo",area="Digital",sobre="",frentes=[{"nome":"Contas","descricao":"x"}],publico="",dna="",estilo_visual="claro",cores={},voz="eu")
ok(c.put("/api/perfis/p1",json=body).status_code==200 and A.buscar_perfil("p1")["voz"]=="eu","salvar voz=eu")
d=g.gerar_post({"formato":"reels","frente":"Contas","tema":"t"}, A.buscar_perfil("p1"))
ok("PRIMEIRA PESSOA" in capt["sys"] and "Nunca fale como" in capt["sys"],"instrução de primeira pessoa enviada à IA")
ok("—" not in d["legenda"] and "–" not in d["legenda"],"legenda sem travessão: "+d["legenda"])
r=d["roteiro_reels"]; txt=json.dumps(r,ensure_ascii=False)
ok("—" not in txt and "–" not in txt and r["cenas"][0]["tempo"]=="0-3s","roteiro sem travessão e tempo intacto: "+r["cenas"][0]["fala"])
ok("—" not in d["slides"][0],"slide sem travessão: "+d["slides"][0])
ok("reparação" in capt["sys"],"regra de reparação no prompt")
body["voz"]="nos"; c.put("/api/perfis/p1",json=body); g.gerar_post({"formato":"carrossel","frente":"Contas","tema":"t"}, A.buscar_perfil("p1"))
ok("INSTITUCIONAL" in capt["sys"],"voz nós enviada à IA")
d=g.gerar_post({"formato":"carrossel","frente":"Contas","tema":"t"}, A.buscar_perfil("p1")); ok(d["roteiro_reels"] is None,"carrossel sem roteiro")
r=c.post("/api/perfis",json={"nome_exibicao":"Novo","modelo":"trabalhista"}); ok(A.buscar_perfil(r.json["id"])["voz"]=="eu","perfil novo nasce em primeira pessoa")

print()
print(f"{len(FALHAS)} falha(s)." if FALHAS else "Todos os testes passaram.")
sys.exit(1 if FALHAS else 0)
