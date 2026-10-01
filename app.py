"""
Estúdio de Posts (nome exibido configurável por APP_NOME no .env).

Contas:
- DONO: vê e administra tudo (convites, prazos, limites, uso e custo de
  IA de cada pessoa). Criado automaticamente a partir de DONO_EMAIL e
  DONO_SENHA_INICIAL no .env.
- CLIENTE: entra por um link de convite, cria a senha, configura o
  próprio perfil (área, temas, público, DNA) e só enxerga o que é dele.
  Tem prazo de acesso (ou ilimitado) e limite de posts/buscas por mês.

Cada PERFIL é um advogado/escritório, com identidade visual, área,
temas, público e DNA próprios. A cobrança fica FORA do sistema (link
da Asaas); aqui só existe a marcação "pagante" e observações.
"""
import io
import json
import os
import re
import hmac
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode, urlparse

from flask import Flask, Response, g, jsonify, redirect, request, send_file, send_from_directory, session
from markupsafe import escape
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from motor import gerar_post, pagamentos, publicador, render_post

BASE = Path(__file__).resolve().parent
DADOS = Path(os.environ.get("DADOS_DIR", BASE / "dados"))
BANCO = DADOS / "estudio.sqlite3"
PASTA_POSTS = DADOS / "posts"
PASTA_AVATARES = DADOS / "avatares"
EXTENSOES_AVATAR = {".png", ".jpg", ".jpeg", ".webp"}

# Preços usados só pra ESTIMAR o custo de IA de cada cliente no painel
# (US$ por milhão de tokens e por busca). Confira os valores atuais em
# https://www.anthropic.com/pricing e ajuste no .env se mudarem.
PRECO_ENTRADA = float(os.environ.get("PRECO_ENTRADA_USD_MTOK", "3"))
PRECO_SAIDA = float(os.environ.get("PRECO_SAIDA_USD_MTOK", "15"))
PRECO_BUSCA = float(os.environ.get("PRECO_BUSCA_USD", "0.01"))
COTACAO_DOLAR = float(os.environ.get("COTACAO_DOLAR", "5.50"))
LIMITE_POSTS_PADRAO = int(os.environ.get("LIMITE_POSTS_MES_PADRAO", "60"))
LIMITE_RADAR_PADRAO = int(os.environ.get("LIMITE_RADAR_MES_PADRAO", "12"))
LIMITE_SUGESTAO_AREA_MES = int(os.environ.get("LIMITE_SUGESTAO_AREA_MES", "10"))
# Planos (valores mensais em R$, mudam pelo .env) e tolerância de atraso.
PLANOS = {
    "essencial": {"nome": "Essencial", "valor": float(os.environ.get("PRECO_ESSENCIAL", "197")),
                  "itens": [f"Até {LIMITE_POSTS_PADRAO} posts por mês, no seu nicho", f"Radar de pautas ({LIMITE_RADAR_PADRAO} buscas por mês)",
                            "Artes prontas e legendas", "📱 Postar pelo celular"]},
    "completo": {"nome": "Completo", "valor": float(os.environ.get("PRECO_COMPLETO", "247")),
                 "itens": ["Tudo do Essencial", "Publicar direto no Instagram", "Agendar posts com data e hora", "Agenda de publicações"]},
}
DIAS_TOLERANCIA = int(os.environ.get("DIAS_TOLERANCIA", "3"))
VALIDADE_CONVITE_DIAS = 7

# Nome do produto mostrado na interface (login, topo, aba do navegador,
# convites). Trocar a marca = mudar APP_NOME no .env e reiniciar.
APP_NOME = (os.environ.get("APP_NOME") or "Estúdio de Posts").strip()[:60] or "Estúdio de Posts"


def _marca_html(nome: str) -> str:
    """Versão do nome pra logo: destaca a última palavra ("Estúdio de
    <span>Posts</span>") ou um sufixo não alfanumérico ("Advoga<span>+</span>").
    Tudo passa por escape, então nenhum caractere do nome vira HTML."""
    partes = nome.split()
    if len(partes) > 1:
        return f"{escape(' '.join(partes[:-1]))} <span>{escape(partes[-1])}</span>"
    corpo = nome.rstrip("+*!.#")
    sufixo = nome[len(corpo):]
    if corpo and sufixo:
        return f"{escape(corpo)}<span>{escape(sufixo)}</span>"
    return str(escape(nome))


def _pagina_html() -> str:
    html = (BASE / "static" / "index.html").read_text(encoding="utf-8")
    # JSON seguro dentro de <script>: sem "<" literal (evita fechar a tag).
    nome_js = json.dumps(APP_NOME, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    return (html.replace("{{APP_NOME}}", str(escape(APP_NOME)))
                .replace("{{APP_MARCA}}", _marca_html(APP_NOME))
                .replace("{{APP_NOME_JSON}}", nome_js))

app = Flask(__name__, static_folder=None)
if os.environ.get("CONFIAR_PROXY", "0") == "1":
    # Atrás do Caddy: confia nos cabeçalhos X-Forwarded-* dele pra saber que
    # o acesso de fora é HTTPS e qual é o domínio. Assim os links de convite
    # já saem com https://. Só ligar quando a porta estiver fechada pro
    # mundo (compose publica em 127.0.0.1) e só o proxy chegar no app.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY", "")
if len(app.secret_key) < 32:
    raise RuntimeError("Defina SECRET_KEY no .env (pelo menos 32 caracteres aleatórios).")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SEGURO", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)


# ═════════════════════════ Banco ═════════════════════════

def conectar():
    con = sqlite3.connect(BANCO, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def iniciar_banco():
    DADOS.mkdir(parents=True, exist_ok=True)
    PASTA_POSTS.mkdir(parents=True, exist_ok=True)
    PASTA_AVATARES.mkdir(parents=True, exist_ok=True)
    with conectar() as con:
        con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT,
                papel TEXT NOT NULL DEFAULT 'cliente',
                status TEXT NOT NULL DEFAULT 'convidado',
                dias_acesso INTEGER,
                acesso_ate TEXT,
                limite_posts_mes INTEGER,
                limite_radar_mes INTEGER,
                pagante INTEGER NOT NULL DEFAULT 0,
                observacao TEXT,
                token_convite TEXT,
                convite_expira TEXT,
                ultimo_acesso TEXT,
                criado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uso_ia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id TEXT,
                perfil_id TEXT,
                tipo TEXT NOT NULL,
                tokens_entrada INTEGER NOT NULL DEFAULT 0,
                tokens_saida INTEGER NOT NULL DEFAULT 0,
                buscas INTEGER NOT NULL DEFAULT 0,
                custo_usd REAL NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS perfis (
                id TEXT PRIMARY KEY,
                nome_exibicao TEXT NOT NULL,
                handle TEXT,
                area TEXT,
                sobre TEXT,
                frentes TEXT,
                publico TEXT,
                dna TEXT,
                estilo_visual TEXT NOT NULL DEFAULT 'escuro',
                cores TEXT,
                avatar TEXT,
                criado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                perfil_id TEXT NOT NULL,
                formato TEXT NOT NULL,
                frente TEXT,
                tema TEXT,
                opcoes TEXT,
                status TEXT NOT NULL,
                titulo_interno TEXT,
                slides TEXT,
                roteiro_reels TEXT,
                legenda TEXT,
                hashtags TEXT,
                alertas TEXT,
                erro TEXT,
                criado_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pautas (
                id TEXT PRIMARY KEY,
                perfil_id TEXT NOT NULL,
                modo TEXT NOT NULL,
                status TEXT NOT NULL,
                pautas TEXT,
                erro TEXT,
                criado_em TEXT NOT NULL
            );
        """)
        colunas = [r[1] for r in con.execute("PRAGMA table_info(perfis)").fetchall()]
        if "usuario_id" not in colunas:
            con.execute("ALTER TABLE perfis ADD COLUMN usuario_id TEXT")
        if "voz" not in colunas:
            con.execute("ALTER TABLE perfis ADD COLUMN voz TEXT NOT NULL DEFAULT 'neutra'")
        for coluna in ("zernio_profile_id", "ig_account_id", "ig_username"):
            if coluna not in colunas:
                con.execute(f"ALTER TABLE perfis ADD COLUMN {coluna} TEXT")
        cols_u = [r[1] for r in con.execute("PRAGMA table_info(usuarios)").fetchall()]
        if "publicacao_auto" not in cols_u:
            con.execute("ALTER TABLE usuarios ADD COLUMN publicacao_auto INTEGER NOT NULL DEFAULT 0")
        for coluna in ("asaas_customer_id", "asaas_subscription_id", "plano", "plano_pendente", "assinatura_status", "asaas_telefone_ok", "asaas_cadastro_ok",
                       "asaas_checkout_pendente", "asaas_assinatura_pendente"):
            if coluna not in cols_u:
                con.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} TEXT")
        con.execute("CREATE TABLE IF NOT EXISTS eventos_pagamento (id TEXT PRIMARY KEY, evento TEXT, recebido_em TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS pagamentos_processados (id TEXT PRIMARY KEY, usuario_id TEXT, processado_em TEXT NOT NULL)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                perfil_id TEXT NOT NULL,
                usuario_id TEXT,
                zernio_post_id TEXT,
                quando TEXT,
                status TEXT NOT NULL,
                url TEXT,
                erro TEXT,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )""")
        con.execute("UPDATE agendamentos SET status='erro', erro='Interrompido (o app foi reiniciado durante o envio). Tente de novo.' WHERE status='enviando'")
        for tabela in ("posts", "pautas"):
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabela})").fetchall()]
            if "usuario_id" not in cols:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN usuario_id TEXT")
        # Gerações que estavam em andamento quando o app foi fechado não
        # têm mais nada rodando por trás -- marca como erro.
        for tabela in ("posts", "pautas"):
            con.execute(f"UPDATE {tabela} SET status='erro', erro='Interrompido (o app foi fechado antes de terminar). Tente de novo.' WHERE status='processando'")
    _garantir_dono()


def _garantir_dono():
    """Cria a conta de dono a partir do .env, se ainda não existir."""
    email = (os.environ.get("DONO_EMAIL") or "").strip().lower()
    senha = os.environ.get("DONO_SENHA_INICIAL") or ""
    with conectar() as con:
        existe = con.execute("SELECT 1 FROM usuarios WHERE papel='dono'").fetchone()
        if existe or not email:
            return
        if len(senha) < 10:
            raise RuntimeError("DONO_SENHA_INICIAL precisa ter pelo menos 10 caracteres.")
        dono_id = uuid.uuid4().hex
        con.execute(
            "INSERT INTO usuarios (id, nome, email, senha_hash, papel, status, criado_em) VALUES (?,?,?,?, 'dono', 'ativo', ?)",
            (dono_id, os.environ.get("DONO_NOME", "Dono"), email, generate_password_hash(senha), agora()),
        )
        # Perfis criados antes de existir login ficam com o dono.
        con.execute("UPDATE perfis SET usuario_id=? WHERE usuario_id IS NULL", (dono_id,))


def agora():
    return datetime.now().isoformat(timespec="seconds")


def _perfil_dict(r) -> dict:
    return {
        "id": r["id"], "nome_exibicao": r["nome_exibicao"], "handle": r["handle"] or "", "area": r["area"] or "",
        "sobre": r["sobre"] or "", "frentes": json.loads(r["frentes"] or "[]"), "publico": r["publico"] or "",
        "dna": r["dna"] or "", "estilo_visual": r["estilo_visual"] or "claro", "cores": json.loads(r["cores"] or "{}"),
        "tem_avatar": bool(r["avatar"]), "avatar": r["avatar"], "criado_em": r["criado_em"],
        "usuario_id": r["usuario_id"], "voz": r["voz"] or "neutra",
        "ig_username": r["ig_username"], "ig_conectado": bool(r["ig_account_id"]),
        "zernio_profile_id": r["zernio_profile_id"], "ig_account_id": r["ig_account_id"],
    }


def buscar_perfil(perfil_id) -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM perfis WHERE id=?", (perfil_id,)).fetchone()
    return _perfil_dict(r) if r else None


def _post_dict(r) -> dict:
    return {
        "id": r["id"], "perfil_id": r["perfil_id"], "formato": r["formato"], "frente": r["frente"], "tema": r["tema"],
        "opcoes": json.loads(r["opcoes"] or "{}"), "status": r["status"], "titulo_interno": r["titulo_interno"],
        "slides": json.loads(r["slides"] or "[]"), "roteiro_reels": json.loads(r["roteiro_reels"]) if r["roteiro_reels"] else None,
        "legenda": r["legenda"] or "", "hashtags": json.loads(r["hashtags"] or "[]"),
        "alertas": json.loads(r["alertas"] or "[]"), "erro": r["erro"], "criado_em": r["criado_em"],
        "usuario_id": r["usuario_id"],
    }


def buscar_post(post_id) -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    return _post_dict(r) if r else None


# ═════════════════════════ Artes ═════════════════════════

def identidade_e_paleta(perfil: dict, sobrescrever: dict | None = None):
    p = dict(perfil)
    p.update({k: v for k, v in (sobrescrever or {}).items() if v not in (None, "")})
    avatar = str(PASTA_AVATARES / p["avatar"]) if p.get("avatar") else None
    identidade = {"nome": p["nome_exibicao"], "handle": p.get("handle") or "", "avatar_path": avatar}
    estilo = p.get("estilo_visual") if p.get("estilo_visual") in render_post.ESTILOS else "claro"
    return identidade, render_post.montar_paleta(estilo, p.get("cores") or {})


def renderizar(post_id: str, dados: dict, perfil: dict):
    pasta = PASTA_POSTS / post_id
    identidade, paleta = identidade_e_paleta(perfil)
    nomes = render_post.desenhar_todos(dados["slides"], identidade, paleta, str(pasta))
    extras = {"legenda.txt": gerar_post.texto_legenda_completa(dados)}
    roteiro = gerar_post.texto_roteiro(dados.get("roteiro_reels"))
    if roteiro:
        extras["roteiro_reels.txt"] = roteiro
    render_post.empacotar_zip(str(pasta), nomes, extras)


# ═════════════════════════ Contas e acesso ═════════════════════════

def _dt(iso):
    return datetime.fromisoformat(iso) if iso else None


def _inicio_mes() -> str:
    return datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def buscar_usuario(usuario_id=None, email=None, token=None):
    with conectar() as con:
        if usuario_id:
            r = con.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        elif email:
            r = con.execute("SELECT * FROM usuarios WHERE email=?", (email.strip().lower(),)).fetchone()
        else:
            r = con.execute("SELECT * FROM usuarios WHERE token_convite=?", (token,)).fetchone()
    return dict(r) if r else None


def situacao_acesso(u: dict) -> str:
    """ativo | convidado | bloqueado | expirado"""
    if u["papel"] == "dono":
        return "ativo"
    if u["status"] in ("convidado", "bloqueado"):
        return u["status"]
    if u["acesso_ate"] and _dt(u["acesso_ate"]) < datetime.now():
        return "expirado"
    return "ativo"


def registrar_uso(usuario_id, perfil_id, tipo, uso: dict):
    uso = uso or {}
    custo = (uso.get("entrada", 0) * PRECO_ENTRADA + uso.get("saida", 0) * PRECO_SAIDA) / 1_000_000 + uso.get("buscas", 0) * PRECO_BUSCA
    with conectar() as con:
        con.execute(
            "INSERT INTO uso_ia (usuario_id, perfil_id, tipo, tokens_entrada, tokens_saida, buscas, custo_usd, criado_em) VALUES (?,?,?,?,?,?,?,?)",
            (usuario_id, perfil_id, tipo, uso.get("entrada", 0), uso.get("saida", 0), uso.get("buscas", 0), custo, agora()),
        )


def contagem_mes(usuario_id, tabela) -> int:
    with conectar() as con:
        return con.execute(
            f"SELECT COUNT(*) FROM {tabela} WHERE usuario_id=? AND criado_em>=? AND status!='erro'",
            (usuario_id, _inicio_mes()),
        ).fetchone()[0]


# Tentativas de login erradas, por IP+e-mail (memória do processo).
_FALHAS = {}
MAX_FALHAS, JANELA_FALHAS = 6, 15 * 60


def _bloqueado_por_falhas(chave) -> bool:
    tentativas = [t for t in _FALHAS.get(chave, []) if time.time() - t < JANELA_FALHAS]
    _FALHAS[chave] = tentativas
    return len(tentativas) >= MAX_FALHAS


@app.before_request
def conferir_origem():
    """Barra requisições que alteram dados vindas de OUTRO site (proteção
    extra contra CSRF, além do cookie SameSite=Lax)."""
    if request.method in ("POST", "PUT", "DELETE"):
        origem = request.headers.get("Origin")
        if origem and urlparse(origem).netloc != request.host:
            return jsonify({"erro": "Origem não permitida."}), 403


def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        uid = session.get("uid")
        u = buscar_usuario(usuario_id=uid) if uid else None
        if not u:
            session.clear()
            return jsonify({"erro": "Faça login.", "codigo": "sem_login"}), 401
        situacao = situacao_acesso(u)
        if situacao != "ativo":
            return jsonify({"erro": "Seu acesso não está ativo.", "codigo": situacao}), 403
        g.usuario = u
        return view(*args, **kwargs)
    return envolvida


def login_conta(view):
    """Como login_obrigatorio, mas deixa passar quem está com o acesso
    vencido: é por aqui que a pessoa vê a tela de assinatura e paga."""
    @wraps(view)
    def envolvida(*args, **kwargs):
        uid = session.get("uid")
        u = buscar_usuario(usuario_id=uid) if uid else None
        if not u:
            session.clear()
            return jsonify({"erro": "Faça login.", "codigo": "sem_login"}), 401
        situacao = situacao_acesso(u)
        if situacao not in ("ativo", "expirado"):
            return jsonify({"erro": "Seu acesso não está ativo.", "codigo": situacao}), 403
        g.usuario = u
        return view(*args, **kwargs)
    return envolvida


def dono_obrigatorio(view):
    @wraps(view)
    @login_obrigatorio
    def envolvida(*args, **kwargs):
        if g.usuario["papel"] != "dono":
            return jsonify({"erro": "Só o dono pode fazer isso."}), 403
        return view(*args, **kwargs)
    return envolvida


def perfil_autorizado(perfil_id):
    """Devolve o perfil se o usuário logado pode mexer nele."""
    perfil = buscar_perfil(perfil_id)
    if not perfil:
        return None
    if g.usuario["papel"] == "dono" or perfil["usuario_id"] == g.usuario["id"]:
        return perfil
    return None


def post_autorizado(post_id):
    post = buscar_post(post_id)
    if post and perfil_autorizado(post["perfil_id"]):
        return post
    return None


def _dados_eu(u: dict) -> dict:
    return {
        "id": u["id"], "nome": u["nome"], "email": u["email"], "papel": u["papel"],
        "acesso_ate": u["acesso_ate"], "situacao": situacao_acesso(u),
        "limite_posts_mes": u["limite_posts_mes"], "limite_radar_mes": u["limite_radar_mes"],
        "posts_mes": contagem_mes(u["id"], "posts"), "radar_mes": contagem_mes(u["id"], "pautas"),
        "publicacao": {"configurada": publicador.configurado(), "liberada": pode_publicar(u)},
        "assinatura": {"configurada": pagamentos.configurado() and u["papel"] != "dono", "plano": u.get("plano"),
                       "status": u.get("assinatura_status"), "pagante": bool(u.get("pagante"))},
    }


def definir_publicacao(usuario_id: str, ativo: bool, con):
    con.execute("UPDATE usuarios SET publicacao_auto=? WHERE id=?", (1 if ativo else 0, usuario_id))
    if not ativo:
        # Sem o upgrade: desconecta os Instagrams dessa pessoa pra parar de
        # pagar por eles na plataforma de publicação.
        contas = con.execute("SELECT id, ig_account_id FROM perfis WHERE usuario_id=? AND ig_account_id IS NOT NULL", (usuario_id,)).fetchall()
        for pid, conta in contas:
            publicador.desconectar(conta)
            con.execute("UPDATE perfis SET ig_account_id=NULL, ig_username=NULL WHERE id=?", (pid,))


def pode_publicar(u: dict) -> bool:
    """Publicação automática: sempre pro dono; pro convidado só se o dono
    liberou (upgrade pago por fora, pela Asaas)."""
    return u["papel"] == "dono" or bool(u.get("publicacao_auto"))


@app.post("/api/login")
def login():
    p = request.get_json(silent=True) or {}
    email = (p.get("email") or "").strip().lower()
    chave = f"{request.remote_addr}|{email}"
    if _bloqueado_por_falhas(chave):
        return jsonify({"erro": "Muitas tentativas. Espere 15 minutos e tente de novo."}), 429
    u = buscar_usuario(email=email) if email else None
    if not u or not u["senha_hash"] or not check_password_hash(u["senha_hash"], p.get("senha") or ""):
        _FALHAS.setdefault(chave, []).append(time.time())
        return jsonify({"erro": "E-mail ou senha inválidos."}), 401
    _FALHAS.pop(chave, None)
    situacao = situacao_acesso(u)
    if situacao == "bloqueado":
        return jsonify({"erro": "Seu acesso está pausado. Fale com quem te convidou.", "codigo": "bloqueado"}), 403
    if situacao == "expirado" and not pagamentos.configurado():
        fim = _dt(u["acesso_ate"]).strftime("%d/%m/%Y")
        return jsonify({"erro": f"Seu período de acesso terminou em {fim}. Fale com quem te convidou pra continuar.", "codigo": "expirado"}), 403
    session.clear()
    session.permanent = True
    session["uid"] = u["id"]
    with conectar() as con:
        con.execute("UPDATE usuarios SET ultimo_acesso=? WHERE id=?", (agora(), u["id"]))
    return jsonify(_dados_eu(u))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/eu")
@login_conta
def eu():
    return jsonify(_dados_eu(g.usuario))


def _convite_valido(token):
    u = buscar_usuario(token=token) if token else None
    if not u or u["status"] == "bloqueado" or not u["convite_expira"] or _dt(u["convite_expira"]) < datetime.now():
        return None
    return u


@app.get("/api/convite/<token>")
def ver_convite(token):
    u = _convite_valido(token)
    if not u:
        return jsonify({"erro": "Link inválido ou expirado. Peça um novo link."}), 404
    return jsonify({"nome": u["nome"], "email": u["email"], "dias_acesso": u["dias_acesso"],
                    "redefinir": u["status"] != "convidado"})


@app.post("/api/convite/<token>")
def aceitar_convite(token):
    u = _convite_valido(token)
    if not u:
        return jsonify({"erro": "Link inválido ou expirado. Peça um novo link."}), 404
    senha = (request.get_json(silent=True) or {}).get("senha") or ""
    if len(senha) < 8:
        return jsonify({"erro": "A senha precisa ter pelo menos 8 caracteres."}), 400
    with conectar() as con:
        if u["status"] == "convidado":
            # Primeiro acesso: o prazo começa a contar a partir de agora.
            acesso_ate = (datetime.now() + timedelta(days=u["dias_acesso"])).isoformat(timespec="seconds") if u["dias_acesso"] else None
            con.execute(
                "UPDATE usuarios SET senha_hash=?, status='ativo', acesso_ate=?, token_convite=NULL, convite_expira=NULL, ultimo_acesso=? WHERE id=?",
                (generate_password_hash(senha), acesso_ate, agora(), u["id"]),
            )
        else:
            # Redefinição de senha: mantém prazo e situação.
            con.execute(
                "UPDATE usuarios SET senha_hash=?, token_convite=NULL, convite_expira=NULL, ultimo_acesso=? WHERE id=?",
                (generate_password_hash(senha), agora(), u["id"]),
            )
    session.clear()
    session.permanent = True
    session["uid"] = u["id"]
    return jsonify(_dados_eu(buscar_usuario(usuario_id=u["id"])))


# ─── Painel do dono ───

def _novo_token():
    return secrets.token_urlsafe(24), (datetime.now() + timedelta(days=VALIDADE_CONVITE_DIAS)).isoformat(timespec="seconds")


def _link_convite(token):
    return request.host_url.rstrip("/") + "/convite/" + token


@app.get("/api/admin/usuarios")
@dono_obrigatorio
def admin_listar():
    inicio = _inicio_mes()
    with conectar() as con:
        usuarios = [dict(r) for r in con.execute("SELECT * FROM usuarios ORDER BY papel='dono' DESC, criado_em DESC").fetchall()]
        saida = []
        for u in usuarios:
            uso_mes = con.execute("SELECT COALESCE(SUM(custo_usd),0) FROM uso_ia WHERE usuario_id=? AND criado_em>=?", (u["id"], inicio)).fetchone()[0]
            uso_total = con.execute("SELECT COALESCE(SUM(custo_usd),0) FROM uso_ia WHERE usuario_id=?", (u["id"],)).fetchone()[0]
            posts_total = con.execute("SELECT COUNT(*) FROM posts WHERE usuario_id=? AND status='concluido'", (u["id"],)).fetchone()[0]
            perfis = [r[0] for r in con.execute("SELECT nome_exibicao FROM perfis WHERE usuario_id=?", (u["id"],)).fetchall()]
            saida.append({
                "id": u["id"], "nome": u["nome"], "email": u["email"], "papel": u["papel"],
                "situacao": situacao_acesso(u), "dias_acesso": u["dias_acesso"], "acesso_ate": u["acesso_ate"],
                "limite_posts_mes": u["limite_posts_mes"], "limite_radar_mes": u["limite_radar_mes"],
                "pagante": bool(u["pagante"]), "observacao": u["observacao"] or "",
                "publicacao_auto": bool(u["publicacao_auto"]),
                "plano": u["plano"], "assinatura_status": u["assinatura_status"],
                "ultimo_acesso": u["ultimo_acesso"], "criado_em": u["criado_em"], "perfis": perfis,
                "posts_mes": contagem_mes(u["id"], "posts"), "radar_mes": contagem_mes(u["id"], "pautas"),
                "posts_total": posts_total, "custo_mes_usd": round(uso_mes, 4), "custo_total_usd": round(uso_total, 4),
                "link_convite": _link_convite(u["token_convite"]) if u["token_convite"] and u["convite_expira"] and _dt(u["convite_expira"]) > datetime.now() else None,
                "convite_expira": u["convite_expira"],
            })
        total_mes = con.execute("SELECT COALESCE(SUM(custo_usd),0) FROM uso_ia WHERE criado_em>=?", (inicio,)).fetchone()[0]
    return jsonify({"usuarios": saida, "custo_mes_usd": round(total_mes, 4), "cotacao_dolar": COTACAO_DOLAR})


def _int_ou_none(v):
    try:
        v = int(v)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


@app.post("/api/admin/usuarios")
@dono_obrigatorio
def admin_convidar():
    p = request.get_json(silent=True) or {}
    nome = (p.get("nome") or "").strip()
    email = (p.get("email") or "").strip().lower()
    if not nome or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"erro": "Informe nome e um e-mail válido."}), 400
    if buscar_usuario(email=email):
        return jsonify({"erro": "Já existe uma pessoa com esse e-mail."}), 400
    token, expira = _novo_token()
    with conectar() as con:
        con.execute(
            "INSERT INTO usuarios (id, nome, email, papel, status, dias_acesso, limite_posts_mes, limite_radar_mes, pagante, observacao, token_convite, convite_expira, criado_em) "
            "VALUES (?,?,?, 'cliente', 'convidado', ?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, nome[:120], email, _int_ou_none(p.get("dias_acesso")),
             _int_ou_none(p.get("limite_posts_mes")) or LIMITE_POSTS_PADRAO, _int_ou_none(p.get("limite_radar_mes")) or LIMITE_RADAR_PADRAO,
             1 if p.get("pagante") else 0, (p.get("observacao") or "").strip()[:500], token, expira, agora()),
        )
    return jsonify({"link_convite": _link_convite(token)}), 201


@app.put("/api/admin/usuarios/<usuario_id>")
@dono_obrigatorio
def admin_alterar(usuario_id):
    u = buscar_usuario(usuario_id=usuario_id)
    if not u or u["papel"] == "dono":
        return jsonify({"erro": "Pessoa não encontrada."}), 404
    p = request.get_json(silent=True) or {}
    acao = p.get("acao")
    with conectar() as con:
        if acao == "estender":
            dias = _int_ou_none(p.get("dias"))
            if not dias:
                return jsonify({"erro": "Informe quantos dias."}), 400
            if u["status"] == "convidado":
                con.execute("UPDATE usuarios SET dias_acesso=COALESCE(dias_acesso,0)+? WHERE id=?", (dias, usuario_id))
            else:
                base = max(_dt(u["acesso_ate"]) or datetime.now(), datetime.now())
                con.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", ((base + timedelta(days=dias)).isoformat(timespec="seconds"), usuario_id))
        elif acao == "ilimitado":
            con.execute("UPDATE usuarios SET acesso_ate=NULL, dias_acesso=NULL WHERE id=?", (usuario_id,))
        elif acao == "encerrar":
            if u["status"] == "convidado":
                con.execute("UPDATE usuarios SET status='bloqueado' WHERE id=?", (usuario_id,))
            else:
                con.execute("UPDATE usuarios SET acesso_ate=? WHERE id=?", (agora(), usuario_id))
        elif acao == "bloquear":
            con.execute("UPDATE usuarios SET status='bloqueado' WHERE id=?", (usuario_id,))
        elif acao == "desbloquear":
            novo = "ativo" if u["senha_hash"] else "convidado"
            con.execute("UPDATE usuarios SET status=? WHERE id=?", (novo, usuario_id))
        elif acao == "novo_convite":
            # Pessoa que ainda não ativou: novo link de convite.
            # Pessoa já ativa (esqueceu a senha): link pra criar senha nova,
            # sem mexer no prazo.
            token, expira = _novo_token()
            con.execute("UPDATE usuarios SET token_convite=?, convite_expira=? WHERE id=?", (token, expira, usuario_id))
            return jsonify({"link_convite": _link_convite(token)})
        elif acao == "publicacao":
            definir_publicacao(usuario_id, bool(p.get("ativo")), con)
        elif acao == "editar":
            con.execute(
                "UPDATE usuarios SET nome=?, limite_posts_mes=?, limite_radar_mes=?, pagante=?, observacao=? WHERE id=?",
                ((p.get("nome") or u["nome"]).strip()[:120], _int_ou_none(p.get("limite_posts_mes")) or LIMITE_POSTS_PADRAO,
                 _int_ou_none(p.get("limite_radar_mes")) or LIMITE_RADAR_PADRAO, 1 if p.get("pagante") else 0,
                 (p.get("observacao") or "").strip()[:500], usuario_id),
            )
        else:
            return jsonify({"erro": "Ação desconhecida."}), 400
    return jsonify({"ok": True})


@app.delete("/api/admin/usuarios/<usuario_id>")
@dono_obrigatorio
def admin_remover(usuario_id):
    u = buscar_usuario(usuario_id=usuario_id)
    if not u or u["papel"] == "dono":
        return jsonify({"erro": "Pessoa não encontrada."}), 404
    with conectar() as con:
        perfis = [r[0] for r in con.execute("SELECT id FROM perfis WHERE usuario_id=?", (usuario_id,)).fetchall()]
    for pid in perfis:
        _apagar_perfil_completo(pid)
    with conectar() as con:
        con.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
    return jsonify({"ok": True})


# ═════════════════════════ Publicação no Instagram (Zernio) ═════════════════════════

FUSO_BR = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019
FINAIS = ("publicado", "erro", "cancelado")


def _exigir_publicacao(perfil):
    if not publicador.configurado():
        return jsonify({"erro": "A publicação automática ainda não foi configurada no servidor."}), 503
    if not pode_publicar(g.usuario):
        return jsonify({"erro": "A publicação automática faz parte do plano Completo. Fale com quem te convidou pra liberar.",
                        "codigo": "sem_upgrade"}), 403
    return None


@app.post("/api/perfis/<perfil_id>/instagram/conectar")
@login_obrigatorio
def conectar_instagram(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    bloqueio = _exigir_publicacao(perfil)
    if bloqueio:
        return bloqueio
    try:
        zid = perfil["zernio_profile_id"]
        if not zid:
            zid = publicador.criar_perfil(f"{perfil['nome_exibicao']} ({perfil_id[:6]})")
            with conectar() as con:
                con.execute("UPDATE perfis SET zernio_profile_id=? WHERE id=?", (zid, perfil_id))
        volta = request.host_url.rstrip("/") + "/instagram/conectado?" + urlencode({"perfil": perfil_id})
        return jsonify({"url": publicador.link_conexao(zid, volta)})
    except publicador.ErroPublicacao as e:
        return jsonify({"erro": str(e)}), 502


@app.get("/instagram/conectado")
def instagram_conectado():
    """O navegador volta pra cá depois do login no Instagram. Nada que vem
    na URL é confiado: a conta é conferida direto na API do Zernio."""
    uid = session.get("uid")
    u = buscar_usuario(usuario_id=uid) if uid else None
    if not u or situacao_acesso(u) != "ativo":
        return redirect("/")
    g.usuario = u
    perfil = perfil_autorizado(request.args.get("perfil", ""))
    if not perfil or not perfil["zernio_profile_id"] or not pode_publicar(u):
        return redirect("/?instagram=erro")
    try:
        contas = [c for c in publicador.contas_instagram(perfil["zernio_profile_id"]) if c.get("_id")]
    except publicador.ErroPublicacao:
        return redirect("/?instagram=erro")
    escolhida = next((c for c in contas if c["_id"] == request.args.get("accountId")), None) or (contas[-1] if contas else None)
    if not escolhida:
        return redirect("/?instagram=erro")
    antiga = perfil["ig_account_id"]
    with conectar() as con:
        con.execute("UPDATE perfis SET ig_account_id=?, ig_username=? WHERE id=?",
                    (escolhida["_id"], (escolhida.get("username") or "")[:80], perfil["id"]))
    if antiga and antiga != escolhida["_id"]:
        publicador.desconectar(antiga)
    return redirect(f"/?instagram=conectado&perfil={perfil['id']}")


@app.post("/api/perfis/<perfil_id>/instagram/desconectar")
@login_obrigatorio
def desconectar_instagram(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    if perfil["ig_account_id"] and publicador.configurado():
        publicador.desconectar(perfil["ig_account_id"])
    with conectar() as con:
        con.execute("UPDATE perfis SET ig_account_id=NULL, ig_username=NULL WHERE id=?", (perfil_id,))
    return jsonify({"ok": True})


def _rodar_publicacao(ag_id, post, perfil, quando):
    try:
        pasta = PASTA_POSTS / post["id"]
        urls = []
        for i in range(1, len(post["slides"]) + 1):
            arquivo = pasta / f"slide_{i:02d}.png"
            urls.append(publicador.enviar_imagem(arquivo.read_bytes(), f"{post['id'][:8]}_{i:02d}.png"))
        legenda = gerar_post.texto_legenda_completa(post)
        r = publicador.criar_post(perfil["ig_account_id"], legenda, urls, quando, id_requisicao=ag_id)
        with conectar() as con:
            con.execute("UPDATE agendamentos SET zernio_post_id=?, status=?, url=?, erro=?, atualizado_em=? WHERE id=?",
                        (r["id"], r["status"], r["url"], r["erro"], agora(), ag_id))
    except publicador.ErroPublicacao as e:
        with conectar() as con:
            con.execute("UPDATE agendamentos SET status='erro', erro=?, atualizado_em=? WHERE id=?", (str(e), agora(), ag_id))
    except Exception as e:
        with conectar() as con:
            con.execute("UPDATE agendamentos SET status='erro', erro=?, atualizado_em=? WHERE id=?",
                        (f"Falha inesperada ({type(e).__name__}). Tente de novo.", agora(), ag_id))


@app.post("/api/posts/<post_id>/publicar")
@login_obrigatorio
def publicar_post(post_id):
    post = post_autorizado(post_id)
    if not post or post["status"] != "concluido":
        return jsonify({"erro": "Post não encontrado ou ainda não concluído."}), 404
    perfil = buscar_perfil(post["perfil_id"])
    bloqueio = _exigir_publicacao(perfil)
    if bloqueio:
        return bloqueio
    if post["formato"] == "reels":
        return jsonify({"erro": "Reels precisa de vídeo, então ainda não dá pra publicar automático. Grave o vídeo e poste pelo app."}), 400
    if not perfil["ig_account_id"]:
        return jsonify({"erro": "Conecte o Instagram deste perfil primeiro (aba Perfil)."}), 400
    quando = (request.get_json(silent=True) or {}).get("quando") or None
    if quando:
        try:
            dt = datetime.strptime(quando, "%Y-%m-%dT%H:%M").replace(tzinfo=FUSO_BR)
        except ValueError:
            return jsonify({"erro": "Data e hora inválidas."}), 400
        agora_br = datetime.now(FUSO_BR)
        if dt < agora_br + timedelta(minutes=5):
            return jsonify({"erro": "Escolha um horário pelo menos 5 minutos no futuro."}), 400
        if dt > agora_br + timedelta(days=180):
            return jsonify({"erro": "Dá pra agendar até 6 meses à frente."}), 400
    with conectar() as con:
        pendentes = con.execute("SELECT COUNT(*) FROM agendamentos WHERE perfil_id=? AND status IN ('enviando','agendado','publicando')",
                                (perfil["id"],)).fetchone()[0]
    if pendentes >= 60:
        return jsonify({"erro": "Esse perfil já tem 60 publicações na fila. Espere algumas saírem."}), 429
    ag_id = uuid.uuid4().hex
    with conectar() as con:
        con.execute("INSERT INTO agendamentos (id, post_id, perfil_id, usuario_id, quando, status, criado_em, atualizado_em) "
                    "VALUES (?,?,?,?,?, 'enviando', ?, ?)", (ag_id, post["id"], perfil["id"], g.usuario["id"], quando, agora(), agora()))
    threading.Thread(target=_rodar_publicacao, args=(ag_id, post, perfil, quando), daemon=True).start()
    return jsonify({"id": ag_id}), 202


def _agendamento_dict(r, titulos) -> dict:
    return {"id": r["id"], "post_id": r["post_id"], "titulo": titulos.get(r["post_id"], "Post"), "quando": r["quando"],
            "status": r["status"], "url": r["url"], "erro": r["erro"], "criado_em": r["criado_em"]}


def _atualizar_status(linhas):
    """Pergunta ao Zernio o status do que ainda não terminou (no máximo
    10 por vez, e só o que não foi conferido no último minuto)."""
    limite = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    agora_br = datetime.now(FUSO_BR).strftime("%Y-%m-%dT%H:%M")
    conferidos = 0
    for r in linhas:
        if conferidos >= 10 or r["status"] in FINAIS or r["status"] == "enviando" or not r["zernio_post_id"]:
            continue
        if r["atualizado_em"] > limite or (r["status"] == "agendado" and r["quando"] and r["quando"] > agora_br):
            continue
        conferidos += 1
        try:
            v = publicador.ver_post(r["zernio_post_id"])
        except publicador.ErroPublicacao:
            continue
        with conectar() as con:
            con.execute("UPDATE agendamentos SET status=?, url=COALESCE(?, url), erro=?, atualizado_em=? WHERE id=?",
                        (v["status"], v["url"], v["erro"], agora(), r["id"]))


@app.get("/api/perfis/<perfil_id>/agenda")
@login_obrigatorio
def agenda(perfil_id):
    if not perfil_autorizado(perfil_id):
        return jsonify({"erro": "Perfil não encontrado."}), 404
    consulta = "SELECT * FROM agendamentos WHERE perfil_id=? ORDER BY COALESCE(quando, substr(criado_em,1,16)) DESC LIMIT 100"
    with conectar() as con:
        linhas = [dict(r) for r in con.execute(consulta, (perfil_id,)).fetchall()]
    if publicador.configurado():
        _atualizar_status(linhas)
        with conectar() as con:
            linhas = [dict(r) for r in con.execute(consulta, (perfil_id,)).fetchall()]
    with conectar() as con:
        titulos = {r["id"]: (r["titulo_interno"] or r["tema"]) for r in con.execute("SELECT id, titulo_interno, tema FROM posts WHERE perfil_id=?", (perfil_id,)).fetchall()}
    return jsonify([_agendamento_dict(r, titulos) for r in linhas])


@app.delete("/api/agendamentos/<ag_id>")
@login_obrigatorio
def cancelar_agendamento(ag_id):
    with conectar() as con:
        r = con.execute("SELECT * FROM agendamentos WHERE id=?", (ag_id,)).fetchone()
    if not r or not perfil_autorizado(r["perfil_id"]):
        return jsonify({"erro": "Agendamento não encontrado."}), 404
    if r["status"] == "publicado":
        return jsonify({"erro": "Esse post já foi publicado. Pra tirar do ar, apague pelo Instagram."}), 400
    if r["status"] == "enviando":
        return jsonify({"erro": "Ainda enviando as artes. Espere alguns segundos e tente de novo."}), 409
    if r["zernio_post_id"] and r["status"] != "cancelado":
        try:
            publicador.cancelar_post(r["zernio_post_id"])
        except publicador.ErroPublicacao as e:
            if r["status"] != "erro":
                return jsonify({"erro": str(e)}), 502
    with conectar() as con:
        con.execute("UPDATE agendamentos SET status='cancelado', atualizado_em=? WHERE id=?", (agora(), ag_id))
    return jsonify({"ok": True})


# ═════════════════════════ Assinatura (Asaas) ═════════════════════════

def _urls_retorno():
    base = request.host_url.rstrip("/")
    return {"sucesso": base + "/?assinatura=sucesso", "cancelado": base + "/?assinatura=cancelada", "expirado": base + "/?assinatura=expirada"}


@app.get("/api/assinatura")
@login_conta
def ver_assinatura():
    u = g.usuario
    return jsonify({
        "configurada": pagamentos.configurado(), "ambiente": pagamentos.ambiente(),
        "planos": [{"id": k, **v} for k, v in PLANOS.items()],
        "plano": u["plano"], "status": u["assinatura_status"], "pagante": bool(u["pagante"]),
        "acesso_ate": u["acesso_ate"], "situacao": situacao_acesso(u), "tem_cadastro": bool(u["asaas_customer_id"]),
        "cadastro_completo": bool(u["asaas_cadastro_ok"]),
        "dados_cobranca": _dados_cobranca_salvos(u),
        "pagamento_pendente": bool(u["asaas_checkout_pendente"] or u["asaas_assinatura_pendente"]),
    })


def _dados_cobranca_salvos(u) -> dict:
    """O que estiver salvo no cadastro do Asaas, pra preencher a tela (só
    pra própria pessoa). Se não houver ou der erro, volta vazio."""
    if not u["asaas_customer_id"] or not pagamentos.configurado():
        return {}
    try:
        c = pagamentos.ver_cliente(u["asaas_customer_id"])
    except pagamentos.ErroPagamento:
        return {}
    return {"cpf_cnpj": c.get("cpfCnpj") or "", "telefone": c.get("mobilePhone") or c.get("phone") or "",
            "cep": pagamentos.so_digitos(c.get("postalCode")), "rua": c.get("address") or "", "numero": c.get("addressNumber") or "",
            "complemento": c.get("complement") or "", "bairro": c.get("province") or ""}


@app.post("/api/assinatura/iniciar")
@login_conta
def iniciar_assinatura():
    u = g.usuario
    if u["papel"] == "dono":
        return jsonify({"erro": "A conta de dono não precisa de assinatura."}), 400
    if not pagamentos.configurado():
        return jsonify({"erro": "O pagamento ainda não foi configurado. Fale com quem te convidou."}), 503
    p = request.get_json(silent=True) or {}
    plano = p.get("plano")
    forma = p.get("forma")
    if plano not in PLANOS or forma not in ("cartao", "pix"):
        return jsonify({"erro": "Escolha o plano e a forma de pagamento."}), 400
    telefone = pagamentos.so_digitos(p.get("telefone"))
    endereco = {k: (str(p.get(k) or "")).strip() for k in ("cep", "rua", "numero", "complemento", "bairro")}
    if forma == "cartao" or not u["asaas_cadastro_ok"]:
        if len(telefone) not in (10, 11):
            return jsonify({"erro": "Informe seu celular com DDD (só números)."}), 400
        if len(pagamentos.so_digitos(endereco["cep"])) != 8 or not endereco["rua"] or not endereco["numero"] or not endereco["bairro"]:
            return jsonify({"erro": "Preencha o endereço: CEP, rua, número e bairro."}), 400
    if forma == "cartao" and len(pagamentos.so_digitos(p.get("cpf_cnpj"))) not in (11, 14):
        return jsonify({"erro": "Informe um CPF ou CNPJ válido (só números)."}), 400
    try:
        cliente = u["asaas_customer_id"]
        if not cliente:
            documento = pagamentos.so_digitos(p.get("cpf_cnpj"))
            if len(documento) not in (11, 14):
                return jsonify({"erro": "Informe um CPF ou CNPJ válido (só números)."}), 400
            cliente = pagamentos.criar_cliente(u["nome"], u["email"], documento, u["id"], telefone, endereco)
            with conectar() as con:
                con.execute("UPDATE usuarios SET asaas_customer_id=?, asaas_cadastro_ok='1' WHERE id=?", (cliente, u["id"]))
        elif not u["asaas_cadastro_ok"]:
            pagamentos.atualizar_cliente(cliente, telefone, endereco)  # cadastro antigo, incompleto
            with conectar() as con:
                con.execute("UPDATE usuarios SET asaas_cadastro_ok='1' WHERE id=?", (u["id"],))
        info = PLANOS[plano]
        nome_plano = f"{APP_NOME} {info['nome']}"
        if forma == "cartao":
            r = pagamentos.checkout_cartao(_dados_pagador(u, cliente, p, telefone, endereco), nome_plano, info["valor"], _urls_retorno(), u["id"])
        else:
            r = pagamentos.assinatura_pix(cliente, nome_plano, info["valor"], u["id"])
    except pagamentos.ErroPagamento as e:
        return jsonify({"erro": str(e)}), 502
    with conectar() as con:
        con.execute("UPDATE usuarios SET plano_pendente=?, asaas_checkout_pendente=?, asaas_assinatura_pendente=? WHERE id=?",
                    (plano, r["id"] if forma == "cartao" else None, r["id"] if forma == "pix" else None, u["id"]))
    registrar_auditoria_pagamento(u["id"], f"checkout_{forma}", plano)
    return jsonify({"url": r["url"]})


@app.get("/api/cep/<cep>")
@login_conta
def consultar_cep(cep):
    try:
        r = pagamentos.buscar_cep(cep)
    except pagamentos.ErroPagamento as e:
        return jsonify({"erro": str(e)}), 502
    if not r:
        return jsonify({"erro": "CEP não encontrado."}), 404
    return jsonify(r)


_ULTIMA_VERIFICACAO: dict = {}


@app.post("/api/assinatura/verificar")
@login_conta
def verificar_pagamento():
    """Rede de segurança: pergunta ao Asaas se o checkout/assinatura que a
    pessoa iniciou já foi pago, sem depender só do webhook."""
    u = g.usuario
    if not pagamentos.configurado() or not (u["asaas_checkout_pendente"] or u["asaas_assinatura_pendente"]):
        return jsonify({"pendente": False})
    if time.time() - _ULTIMA_VERIFICACAO.get(u["id"], 0) < 4:
        return jsonify({"pendente": True, "aguarde": True})
    _ULTIMA_VERIFICACAO[u["id"]] = time.time()
    try:
        pagos = pagamentos.pagamentos_confirmados(u["asaas_checkout_pendente"], u["asaas_assinatura_pendente"])
    except pagamentos.ErroPagamento as e:
        return jsonify({"pendente": True, "erro": str(e)})
    resultado = None
    for pag in pagos:
        if pag.get("customer"):
            # O checkout/assinatura é desta pessoa (foi o sistema que abriu),
            # então o cliente do pagamento é dela.
            with conectar() as con:
                con.execute("UPDATE usuarios SET asaas_customer_id=?, asaas_cadastro_ok='1' WHERE id=?", (pag["customer"], u["id"]))
        resultado = processar_evento_pagamento({"event": "PAYMENT_CONFIRMED", "payment": pag})
    return jsonify({"pendente": not pagos, "resultado": resultado})


@app.post("/api/assinatura/cancelar")
@login_conta
def cancelar_minha_assinatura():
    u = g.usuario
    if not u["asaas_subscription_id"]:
        return jsonify({"erro": "Você não tem uma assinatura ativa."}), 400
    pagamentos.cancelar_assinatura(u["asaas_subscription_id"])
    with conectar() as con:
        con.execute("UPDATE usuarios SET assinatura_status='cancelada' WHERE id=?", (u["id"],))
    fim = _dt(u["acesso_ate"]).strftime("%d/%m/%Y") if u["acesso_ate"] else None
    return jsonify({"ok": True, "acesso_ate": fim})


def _dados_pagador(u, cliente_id, p, telefone, endereco) -> dict:
    """Dados completos do pagador pro checkout do cartão, sempre do
    formulário (que já vem preenchido com o que estava salvo)."""
    cep = pagamentos.buscar_cep(endereco.get("cep") or "")
    if not cep or not cep.get("ibge"):
        raise pagamentos.ErroPagamento("CEP não encontrado. Confira o CEP do endereço de cobrança.")
    return {**endereco, "telefone": telefone, "cpf_cnpj": p.get("cpf_cnpj"), "nome": u["nome"], "email": u["email"], "ibge": cep["ibge"]}


def _vincular_cliente_desconhecido(customer_id: str):
    """O checkout do cartão cria o cliente do lado do Asaas. Quando chega um
    pagamento de um cliente que ainda não conhecemos, consulta o cadastro no
    Asaas e associa à pessoa pelo e-mail (único no sistema)."""
    try:
        c = pagamentos.ver_cliente(customer_id)
    except pagamentos.ErroPagamento:
        return None
    email = (c.get("email") or "").strip().lower()
    if not email:
        return None
    with conectar() as con:
        # Só quem iniciou um pagamento pelo sistema (plano_pendente) e ainda não concluiu.
        r = con.execute("SELECT * FROM usuarios WHERE lower(email)=? AND papel!='dono' AND plano_pendente IS NOT NULL", (email,)).fetchone()
        if not r:
            return None
        con.execute("UPDATE usuarios SET asaas_customer_id=?, asaas_cadastro_ok='1' WHERE id=?", (customer_id, r["id"]))
    return buscar_usuario(usuario_id=r["id"])


def registrar_auditoria_pagamento(usuario_id, tipo, detalhe=""):
    app.logger.info("pagamento usuario=%s tipo=%s %s", usuario_id, tipo, detalhe)


def _plano_do_pagamento(u: dict, valor: float) -> str:
    """O plano escolhido no checkout; se não houver, deduz pelo valor."""
    if u.get("plano_pendente") in PLANOS:
        return u["plano_pendente"]
    if u.get("plano") in PLANOS:
        return u["plano"]
    return "completo" if valor >= PLANOS["completo"]["valor"] - 0.01 else "essencial"


def processar_evento_pagamento(evento: dict) -> str:
    """Aplica um aviso do Asaas. Devolve o que foi feito (pra log/testes)."""
    tipo = evento.get("event") or ""
    pag = evento.get("payment") or {}
    sub = evento.get("subscription") or {}
    cliente = pag.get("customer") or sub.get("customer")
    if not cliente:
        return "ignorado"
    with conectar() as con:
        r = con.execute("SELECT * FROM usuarios WHERE asaas_customer_id=?", (cliente,)).fetchone()
    u = dict(r) if r else _vincular_cliente_desconhecido(cliente)
    if not u:
        return "cliente_desconhecido"

    if tipo in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        if pag.get("id"):
            with conectar() as con:
                if con.execute("SELECT 1 FROM pagamentos_processados WHERE id=?", (pag["id"],)).fetchone():
                    return "ja_processado"
                con.execute("INSERT INTO pagamentos_processados (id, usuario_id, processado_em) VALUES (?,?,?)", (pag["id"], u["id"], agora()))
        valor = float(pag.get("value") or 0)
        plano = _plano_do_pagamento(u, valor)
        try:
            vencimento = datetime.strptime((pag.get("dueDate") or "")[:10], "%Y-%m-%d")
        except ValueError:
            vencimento = datetime.now()
        base = max(datetime.now(), vencimento)
        novo_fim = base + timedelta(days=31 + DIAS_TOLERANCIA)
        atual = _dt(u["acesso_ate"])
        if u["acesso_ate"] is None and u["papel"] != "dono" and u["status"] == "ativo" and not u["pagante"]:
            atual = None  # cortesia sem prazo vira mensal ao assinar
        if atual and atual > novo_fim:
            novo_fim = atual
        assinatura_nova = pag.get("subscription")
        antiga = u["asaas_subscription_id"]
        with conectar() as con:
            con.execute(
                "UPDATE usuarios SET status=CASE WHEN status='convidado' THEN status ELSE 'ativo' END, acesso_ate=?, pagante=1, plano=?, "
                "plano_pendente=NULL, asaas_checkout_pendente=NULL, asaas_assinatura_pendente=NULL, "
                "assinatura_status='ativa', asaas_subscription_id=COALESCE(?, asaas_subscription_id) WHERE id=?",
                (novo_fim.isoformat(timespec="seconds"), plano, assinatura_nova, u["id"]),
            )
            definir_publicacao(u["id"], plano == "completo", con)
        if assinatura_nova and antiga and antiga != assinatura_nova:
            pagamentos.cancelar_assinatura(antiga)  # trocou de plano: encerra a anterior
        return f"pago:{plano}"

    if tipo == "PAYMENT_OVERDUE":
        with conectar() as con:
            con.execute("UPDATE usuarios SET assinatura_status='atrasada' WHERE id=?", (u["id"],))
        return "atrasado"

    if tipo in ("PAYMENT_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED"):
        with conectar() as con:
            con.execute("UPDATE usuarios SET assinatura_status='estornada', acesso_ate=?, pagante=0 WHERE id=?", (agora(), u["id"]))
            definir_publicacao(u["id"], False, con)
        return "estornado"

    if tipo in ("SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"):
        if sub.get("id") and sub.get("id") == u["asaas_subscription_id"]:
            with conectar() as con:
                con.execute("UPDATE usuarios SET assinatura_status='cancelada' WHERE id=?", (u["id"],))
            return "cancelada"
        return "ignorado"
    return "ignorado"


@app.post("/webhooks/asaas")
def webhook_asaas():
    esperado = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")
    recebido = request.headers.get("asaas-access-token", "")
    if len(esperado) < 32 or not hmac.compare_digest(esperado, recebido):
        return jsonify({"erro": "não autorizado"}), 401
    evento = request.get_json(silent=True) or {}
    evento_id = str(evento.get("id") or "")
    if evento_id:
        with conectar() as con:
            if con.execute("SELECT 1 FROM eventos_pagamento WHERE id=?", (evento_id,)).fetchone():
                return jsonify({"ok": True, "repetido": True})
    resultado = processar_evento_pagamento(evento)
    if evento_id:
        with conectar() as con:
            con.execute("INSERT OR IGNORE INTO eventos_pagamento (id, evento, recebido_em) VALUES (?,?,?)",
                        (evento_id, evento.get("event"), agora()))
    return jsonify({"ok": True, "resultado": resultado})


# ═════════════════════════ Páginas ═════════════════════════

@app.get("/")
@app.get("/convite/<_token>")
def pagina(_token=None):
    resp = Response(_pagina_html(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/opcoes")
@login_obrigatorio
def opcoes():
    return jsonify({
        "formatos": list(gerar_post.FORMATOS.items()),
        "estilos_escrita": list(gerar_post.ESTILOS_ESCRITA.items()),
        "modelos_perfil": [[k, v["rotulo"]] for k, v in gerar_post.MODELOS_PERFIL.items()],
        "vozes": list(gerar_post.VOZES.items()),
        "chave_configurada": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    })


# ═════════════════════════ Perfis ═════════════════════════

def _limpar_frentes(frentes) -> list:
    saida, vistos = [], set()
    for f in frentes or []:
        nome = str((f or {}).get("nome", "")).strip()[:60]
        if nome and nome not in vistos:
            vistos.add(nome)
            saida.append({"nome": nome, "descricao": str(f.get("descricao", "")).strip()[:300]})
    return saida[:12] or [{"nome": "Geral", "descricao": ""}]


def _limpar_cores(cores) -> dict:
    return {k: v for k, v in (cores or {}).items()
            if k in ("fundo", "texto", "destaque") and re.fullmatch(r"#[0-9A-Fa-f]{6}", v or "")}


@app.get("/api/perfis")
@login_obrigatorio
def listar_perfis():
    with conectar() as con:
        if g.usuario["papel"] == "dono":
            linhas = con.execute("SELECT p.*, u.nome AS dono_nome, u.papel AS dono_papel FROM perfis p LEFT JOIN usuarios u ON u.id=p.usuario_id "
                                 "ORDER BY u.papel='dono' DESC, p.nome_exibicao COLLATE NOCASE").fetchall()
        else:
            linhas = con.execute("SELECT p.*, NULL AS dono_nome, NULL AS dono_papel FROM perfis p WHERE usuario_id=?", (g.usuario["id"],)).fetchall()
    inicio = _inicio_mes()
    saida = []
    with conectar() as con:
        for r in linhas:
            d = {k: v for k, v in _perfil_dict(r).items() if k not in ("avatar", "zernio_profile_id", "ig_account_id")}
            d["de_cliente"] = r["dono_papel"] == "cliente"
            d["cliente_nome"] = r["dono_nome"] if d["de_cliente"] else None
            d.update(_resumo_perfil(con, d, r["avatar"], inicio))
            if d["de_cliente"]:
                dono_conta = buscar_usuario(usuario_id=r["usuario_id"])
                d["cliente_situacao"] = situacao_acesso(dono_conta) if dono_conta else None
                d["cliente_acesso_ate"] = dono_conta["acesso_ate"] if dono_conta else None
            saida.append(d)
    return jsonify(saida)


def _resumo_perfil(con, perfil: dict, avatar: str | None, inicio_mes: str) -> dict:
    """Informações pra tela de escolha de perfil: uso, cor da marca e o
    quanto o perfil está completo (o que mais influencia a qualidade)."""
    uso = con.execute(
        "SELECT COUNT(*), MAX(criado_em), SUM(CASE WHEN criado_em>=? THEN 1 ELSE 0 END) "
        "FROM posts WHERE perfil_id=? AND status='concluido'",
        (inicio_mes, perfil["id"]),
    ).fetchone()
    paleta = render_post.montar_paleta(perfil["estilo_visual"], perfil["cores"])
    itens = [
        ("Foto de perfil", bool(avatar)),
        ("@ do Instagram", bool(perfil["handle"])),
        ("Área de atuação", bool(perfil["area"])),
        ("Sobre o advogado", bool((perfil["sobre"] or "").strip())),
        ("Público", len((perfil["publico"] or "").strip()) > 80),
        ("DNA de escrita", len((perfil["dna"] or "").strip()) > 200),
    ]
    versao_avatar = None
    if avatar and (PASTA_AVATARES / avatar).exists():
        versao_avatar = int((PASTA_AVATARES / avatar).stat().st_mtime)
    return {
        "posts_total": uso[0] or 0,
        "ultimo_post_em": uso[1],
        "posts_mes": uso[2] or 0,
        "cor_destaque": paleta["destaque"],
        "cor_fundo": paleta["fundo"],
        "avatar_versao": versao_avatar,
        "completo_pct": round(100 * sum(1 for _, feito in itens if feito) / len(itens)),
        "falta": [nome for nome, feito in itens if not feito],
    }


@app.post("/api/perfis")
@login_obrigatorio
def criar_perfil():
    if g.usuario["papel"] != "dono":
        with conectar() as con:
            if con.execute("SELECT 1 FROM perfis WHERE usuario_id=?", (g.usuario["id"],)).fetchone():
                return jsonify({"erro": "Sua conta já tem um perfil."}), 400
    payload = request.get_json(silent=True) or {}
    nome = (payload.get("nome_exibicao") or "").strip()
    if not nome:
        return jsonify({"erro": "Informe o nome exibido."}), 400
    modelo = dict(gerar_post.MODELOS_PERFIL.get(payload.get("modelo") or "em_branco", gerar_post.MODELOS_PERFIL["em_branco"]))
    aviso = None
    area_outra = (payload.get("area_outra") or "").strip()[:120]
    if (payload.get("modelo") or "em_branco") == "em_branco" and area_outra:
        # Área que não está na lista: a IA monta temas e público.
        modelo["area"] = area_outra
        try:
            sugestao, uso = gerar_post.sugerir_area(area_outra)
            registrar_uso(g.usuario["id"], None, "sugestao_area", uso)
            modelo.update({"area": sugestao["area"], "frentes": sugestao["frentes"], "publico": sugestao["publico"]})
        except Exception:
            aviso = "Não consegui montar os temas da sua área agora. Use o botão \"Sugerir com IA\" na aba Perfil."
    perfil_id = uuid.uuid4().hex
    with conectar() as con:
        con.execute(
            "INSERT INTO perfis (id, nome_exibicao, handle, area, sobre, frentes, publico, dna, estilo_visual, cores, criado_em, usuario_id, voz) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (perfil_id, nome[:120], (payload.get("handle") or "").strip()[:80], modelo["area"], "",
             json.dumps(modelo["frentes"], ensure_ascii=False), modelo["publico"], "", "claro", "{}", agora(), g.usuario["id"],
             payload.get("voz") if payload.get("voz") in gerar_post.VOZES else "eu"),
        )
    return jsonify({"id": perfil_id, "aviso": aviso}), 201


@app.post("/api/perfis/<perfil_id>/sugerir_area")
@login_obrigatorio
def sugerir_area(perfil_id):
    """Sugere temas e público pra área informada. NÃO salva: a tela
    preenche o formulário e a pessoa revisa antes de salvar."""
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    if g.usuario["papel"] != "dono":
        with conectar() as con:
            usadas = con.execute("SELECT COUNT(*) FROM uso_ia WHERE usuario_id=? AND tipo='sugestao_area' AND criado_em>=?",
                                 (g.usuario["id"], _inicio_mes())).fetchone()[0]
        if usadas >= LIMITE_SUGESTAO_AREA_MES:
            return jsonify({"erro": "Você chegou ao limite de sugestões automáticas deste mês."}), 429
    p = request.get_json(silent=True) or {}
    area = (p.get("area") or perfil["area"] or "").strip()
    if not area:
        return jsonify({"erro": "Escreva sua área de atuação primeiro."}), 400
    try:
        sugestao, uso = gerar_post.sugerir_area(area, p.get("sobre") or perfil["sobre"])
    except Exception as e:
        return jsonify({"erro": f"Não consegui montar a sugestão agora ({type(e).__name__}). Tente de novo."}), 502
    registrar_uso(perfil["usuario_id"] if g.usuario["papel"] == "dono" else g.usuario["id"], perfil_id, "sugestao_area", uso)
    return jsonify(sugestao)


@app.put("/api/perfis/<perfil_id>")
@login_obrigatorio
def salvar_perfil(perfil_id):
    if not perfil_autorizado(perfil_id):
        return jsonify({"erro": "Perfil não encontrado."}), 404
    p = request.get_json(silent=True) or {}
    nome = (p.get("nome_exibicao") or "").strip()
    if not nome:
        return jsonify({"erro": "Informe o nome exibido."}), 400
    estilo = p.get("estilo_visual") if p.get("estilo_visual") in render_post.ESTILOS else "claro"
    with conectar() as con:
        con.execute(
            "UPDATE perfis SET nome_exibicao=?, handle=?, area=?, sobre=?, frentes=?, publico=?, dna=?, estilo_visual=?, cores=?, voz=? WHERE id=?",
            (nome[:120], (p.get("handle") or "").strip()[:80], (p.get("area") or "").strip()[:200],
             (p.get("sobre") or "").strip()[:2000], json.dumps(_limpar_frentes(p.get("frentes")), ensure_ascii=False),
             (p.get("publico") or "").strip()[:12000], (p.get("dna") or "").strip()[:20000], estilo,
             json.dumps(_limpar_cores(p.get("cores"))), p.get("voz") if p.get("voz") in gerar_post.VOZES else "neutra", perfil_id),
        )
    return jsonify({"ok": True})


def _apagar_perfil_completo(perfil_id):
    perfil = buscar_perfil(perfil_id)
    if not perfil:
        return
    with conectar() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM posts WHERE perfil_id=?", (perfil_id,)).fetchall()]
        con.execute("DELETE FROM posts WHERE perfil_id=?", (perfil_id,))
        con.execute("DELETE FROM pautas WHERE perfil_id=?", (perfil_id,))
        con.execute("DELETE FROM perfis WHERE id=?", (perfil_id,))
    for pid in ids:
        shutil.rmtree(PASTA_POSTS / pid, ignore_errors=True)
    if perfil.get("avatar"):
        (PASTA_AVATARES / perfil["avatar"]).unlink(missing_ok=True)
    if perfil.get("ig_account_id") and publicador.configurado():
        publicador.desconectar(perfil["ig_account_id"])  # para de pagar pela conta
    with conectar() as con:
        con.execute("DELETE FROM agendamentos WHERE perfil_id=?", (perfil_id,))


@app.delete("/api/perfis/<perfil_id>")
@dono_obrigatorio
def apagar_perfil(perfil_id):
    if not buscar_perfil(perfil_id):
        return jsonify({"erro": "Perfil não encontrado."}), 404
    _apagar_perfil_completo(perfil_id)
    return jsonify({"ok": True})


@app.post("/api/perfis/<perfil_id>/avatar")
@login_obrigatorio
def enviar_avatar(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    arquivo = request.files.get("avatar")
    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Envie a imagem."}), 400
    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in EXTENSOES_AVATAR:
        return jsonify({"erro": "Use PNG, JPG ou WEBP."}), 400
    if perfil.get("avatar"):
        (PASTA_AVATARES / perfil["avatar"]).unlink(missing_ok=True)
    nome = f"{perfil_id}{ext}"
    arquivo.save(PASTA_AVATARES / nome)
    with conectar() as con:
        con.execute("UPDATE perfis SET avatar=? WHERE id=?", (nome, perfil_id))
    return jsonify({"ok": True})


@app.get("/api/perfis/<perfil_id>/avatar")
@login_obrigatorio
def ver_avatar(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil or not perfil.get("avatar") or not (PASTA_AVATARES / perfil["avatar"]).exists():
        return jsonify({"erro": "Sem foto."}), 404
    resp = send_file(PASTA_AVATARES / perfil["avatar"])
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@app.post("/api/perfis/<perfil_id>/previa")
@login_obrigatorio
def previa(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    p = request.get_json(silent=True) or {}
    identidade, paleta = identidade_e_paleta(perfil, {
        "nome_exibicao": p.get("nome_exibicao"), "handle": p.get("handle"),
        "estilo_visual": p.get("estilo_visual"), "cores": _limpar_cores(p.get("cores")) or None,
    })
    texto = "Esse é o visual das suas artes.\n\nPalavras importantes aparecem em **destaque**, assim.\n\nSalva esse post pra consultar depois."
    tmp = DADOS / f"previa_{uuid.uuid4().hex}.png"
    try:
        render_post.desenhar_slide(texto, identidade, paleta, str(tmp))
        dados = tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)
    return send_file(io.BytesIO(dados), mimetype="image/png")


# ═════════════════════════ Radar de pautas ═════════════════════════

def _rodar_pautas(pauta_id, modo, frentes, perfil):
    try:
        pautas, uso = gerar_post.buscar_pautas(modo, frentes, perfil)
        registrar_uso(perfil["usuario_id"], perfil["id"], "radar_" + modo, uso)
        with conectar() as con:
            con.execute("UPDATE pautas SET status='concluido', pautas=? WHERE id=?", (json.dumps(pautas, ensure_ascii=False), pauta_id))
    except Exception as e:
        with conectar() as con:
            con.execute("UPDATE pautas SET status='erro', erro=? WHERE id=?", (f"{type(e).__name__}: {e}", pauta_id))


def _limite_estourado(tabela, campo_limite):
    u = g.usuario
    if u["papel"] == "dono":
        return None
    limite = u[campo_limite] or (LIMITE_POSTS_PADRAO if tabela == "posts" else LIMITE_RADAR_PADRAO)
    if contagem_mes(u["id"], tabela) >= limite:
        oque = "posts" if tabela == "posts" else "buscas de pautas"
        return jsonify({"erro": f"Você chegou ao limite de {limite} {oque} deste mês. Fale com quem te convidou se precisar de mais."}), 429
    return None


@app.post("/api/perfis/<perfil_id>/pautas")
@login_obrigatorio
def criar_pautas(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    estourou = _limite_estourado("pautas", "limite_radar_mes")
    if estourou:
        return estourou
    p = request.get_json(silent=True) or {}
    modo = p.get("modo") if p.get("modo") in ("noticias", "ideias") else "noticias"
    pauta_id = uuid.uuid4().hex
    with conectar() as con:
        con.execute("INSERT INTO pautas (id, perfil_id, modo, status, criado_em, usuario_id) VALUES (?,?,?, 'processando', ?, ?)",
                    (pauta_id, perfil_id, modo, agora(), perfil["usuario_id"]))
    threading.Thread(target=_rodar_pautas, args=(pauta_id, modo, p.get("frentes") or [], perfil), daemon=True).start()
    return jsonify({"id": pauta_id}), 202


@app.get("/api/perfis/<perfil_id>/pautas")
@login_obrigatorio
def listar_pautas(perfil_id):
    if not perfil_autorizado(perfil_id):
        return jsonify({"erro": "Perfil não encontrado."}), 404
    with conectar() as con:
        linhas = con.execute("SELECT * FROM pautas WHERE perfil_id=? ORDER BY criado_em DESC LIMIT 10", (perfil_id,)).fetchall()
    return jsonify([{"id": r["id"], "modo": r["modo"], "status": r["status"], "pautas": json.loads(r["pautas"] or "[]"),
                     "erro": r["erro"], "criado_em": r["criado_em"]} for r in linhas])


# ═════════════════════════ Posts ═════════════════════════

def _rodar_post(post_id, opcoes, perfil):
    try:
        dados = gerar_post.gerar_post(opcoes, perfil)
        registrar_uso(perfil["usuario_id"], perfil["id"], "post", dados.pop("_uso", None))
        renderizar(post_id, dados, perfil)
        with conectar() as con:
            con.execute(
                "UPDATE posts SET status='concluido', titulo_interno=?, slides=?, roteiro_reels=?, legenda=?, hashtags=?, alertas=? WHERE id=?",
                ((dados.get("titulo_interno") or "")[:200], json.dumps(dados["slides"], ensure_ascii=False),
                 json.dumps(dados.get("roteiro_reels"), ensure_ascii=False) if dados.get("roteiro_reels") else None,
                 dados.get("legenda"), json.dumps(dados.get("hashtags") or [], ensure_ascii=False),
                 json.dumps(dados.get("alertas") or [], ensure_ascii=False), post_id),
            )
    except Exception as e:
        with conectar() as con:
            con.execute("UPDATE posts SET status='erro', erro=? WHERE id=?", (f"{type(e).__name__}: {e}", post_id))


@app.post("/api/perfis/<perfil_id>/posts")
@login_obrigatorio
def criar_post(perfil_id):
    perfil = perfil_autorizado(perfil_id)
    if not perfil:
        return jsonify({"erro": "Perfil não encontrado."}), 404
    estourou = _limite_estourado("posts", "limite_posts_mes")
    if estourou:
        return estourou
    p = request.get_json(silent=True) or {}
    if p.get("formato") not in gerar_post.FORMATOS:
        return jsonify({"erro": "Formato inválido."}), 400
    nomes_frentes = [f["nome"] for f in perfil["frentes"]]
    frente = p.get("frente") if p.get("frente") in nomes_frentes else (nomes_frentes[0] if nomes_frentes else "Geral")
    noticia = p.get("noticia") if isinstance(p.get("noticia"), dict) else None
    tema = (p.get("tema") or "").strip()
    tem_pele = any((p.get(k) or "").strip() for k in ("pele_quem", "pele_momento", "pele_observacao"))
    if not tema and not noticia and not tem_pele:
        return jsonify({"erro": "Informe um tema, escolha uma pauta do radar ou preencha \"Na pele do cliente\"."}), 400
    opcoes = {
        "formato": p["formato"], "frente": frente, "tema": tema[:500],
        "estilo_escrita": p.get("estilo_escrita") if p.get("estilo_escrita") in gerar_post.ESTILOS_ESCRITA else "educativo",
        "n_slides": p.get("n_slides") or 7, "cta": (p.get("cta") or "").strip()[:200],
        "pele_quem": (p.get("pele_quem") or "").strip()[:300], "pele_momento": (p.get("pele_momento") or "").strip()[:500],
        "pele_observacao": (p.get("pele_observacao") or "").strip()[:500],
        "noticia": {k: str(noticia.get(k, ""))[:600] for k in ("titulo", "resumo", "fonte_nome", "fonte_url", "angulo")} if noticia else None,
    }
    post_id = uuid.uuid4().hex
    tema_registro = tema or (opcoes["noticia"] or {}).get("titulo") or opcoes["pele_momento"] or "Na pele do cliente"
    with conectar() as con:
        con.execute("INSERT INTO posts (id, perfil_id, formato, frente, tema, opcoes, status, criado_em, usuario_id) VALUES (?,?,?,?,?,?, 'processando', ?, ?)",
                    (post_id, perfil_id, p["formato"], frente, tema_registro, json.dumps(opcoes, ensure_ascii=False), agora(), perfil["usuario_id"]))
    threading.Thread(target=_rodar_post, args=(post_id, opcoes, perfil), daemon=True).start()
    return jsonify({"id": post_id}), 202


@app.get("/api/perfis/<perfil_id>/posts")
@login_obrigatorio
def listar_posts(perfil_id):
    if not perfil_autorizado(perfil_id):
        return jsonify({"erro": "Perfil não encontrado."}), 404
    with conectar() as con:
        linhas = con.execute("SELECT * FROM posts WHERE perfil_id=? ORDER BY criado_em DESC LIMIT 200", (perfil_id,)).fetchall()
    return jsonify([{k: v for k, v in _post_dict(r).items() if k in ("id", "formato", "frente", "tema", "titulo_interno", "status", "criado_em")} for r in linhas])


@app.get("/api/posts/<post_id>")
@login_obrigatorio
def detalhe_post(post_id):
    post = post_autorizado(post_id)
    return (jsonify(post), 200) if post else (jsonify({"erro": "Post não encontrado."}), 404)


@app.put("/api/posts/<post_id>/textos")
@login_obrigatorio
def editar_post(post_id):
    post = post_autorizado(post_id)
    if not post or post["status"] != "concluido":
        return jsonify({"erro": "Post não encontrado ou ainda não concluído."}), 404
    perfil = buscar_perfil(post["perfil_id"])
    p = request.get_json(silent=True) or {}
    slides = [str(s).strip() for s in (p.get("slides") or post["slides"]) if str(s).strip()][:15]
    if not slides:
        return jsonify({"erro": "O post precisa de pelo menos um slide com texto."}), 400
    legenda = p.get("legenda", post["legenda"])
    renderizar(post_id, {"slides": slides, "legenda": legenda, "hashtags": post["hashtags"], "roteiro_reels": post["roteiro_reels"]}, perfil)
    with conectar() as con:
        con.execute("UPDATE posts SET slides=?, legenda=? WHERE id=?", (json.dumps(slides, ensure_ascii=False), legenda, post_id))
    return jsonify({"ok": True})


@app.get("/api/posts/<post_id>/slide/<int:numero>")
@login_obrigatorio
def ver_slide(post_id, numero):
    if not post_autorizado(post_id):
        return jsonify({"erro": "Slide não encontrado."}), 404
    caminho = PASTA_POSTS / secure_filename(post_id) / f"slide_{numero:02d}.png"
    if not caminho.exists():
        return jsonify({"erro": "Slide não encontrado."}), 404
    resp = send_file(caminho, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/posts/<post_id>/arquivo")
@login_obrigatorio
def baixar_zip(post_id):
    post = post_autorizado(post_id)
    caminho = PASTA_POSTS / secure_filename(post_id) / "post.zip"
    if not post or not caminho.exists():
        return jsonify({"erro": "Arquivo não disponível."}), 404
    perfil = buscar_perfil(post["perfil_id"]) or {"nome_exibicao": "perfil"}
    nome = secure_filename(f"{perfil['nome_exibicao']} - {post['titulo_interno'] or post['tema']}"[:80]) or "post"
    return send_file(caminho, as_attachment=True, download_name=f"{nome}.zip")


@app.delete("/api/posts/<post_id>")
@login_obrigatorio
def apagar_post(post_id):
    if not post_autorizado(post_id):
        return jsonify({"erro": "Post não encontrado."}), 404
    with conectar() as con:
        con.execute("DELETE FROM posts WHERE id=?", (post_id,))
    shutil.rmtree(PASTA_POSTS / secure_filename(post_id), ignore_errors=True)
    return jsonify({"ok": True})


iniciar_banco()

if __name__ == "__main__":
    # HOST=0.0.0.0 só dentro do Docker; a porta do compose é publicada em
    # 127.0.0.1, então continua acessível SÓ deste computador.
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORTA", "5100")), threaded=True)
