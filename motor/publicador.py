"""
publicador.py — publicação e agendamento no Instagram pela API do Zernio
(https://docs.zernio.com). Usa só a biblioteca padrão do Python.

Como o Zernio organiza as coisas:
- PROFILE: um "grupo" de contas; criamos um por perfil do Advoga+ (grátis).
- ACCOUNT: a conta do Instagram conectada (é o que o Zernio cobra).
- A conexão é feita pelo próprio advogado numa página de login do
  Instagram (authUrl); depois o navegador volta pro nosso redirect_url.
- As artes sobem direto pro armazenamento do Zernio por um link
  temporário (presign + PUT), então nunca ficam públicas no nosso servidor.

Regras do Instagram (valem pra qualquer ferramenta): conta profissional
(Empresa ou Criador), todo post precisa de imagem, carrossel até 10 itens.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("ZERNIO_BASE_URL", "https://zernio.com/api/v1").rstrip("/")
FUSO = os.environ.get("FUSO_HORARIO", "America/Sao_Paulo")
TIMEOUT = 60


class ErroPublicacao(Exception):
    """Erro com mensagem já pronta pra mostrar pro usuário."""


def configurado() -> bool:
    return bool(os.environ.get("ZERNIO_API_KEY", "").strip())


def _chave() -> str:
    chave = os.environ.get("ZERNIO_API_KEY", "").strip()
    if not chave:
        raise ErroPublicacao("A publicação automática ainda não foi configurada no servidor.")
    return chave


def _requisicao(metodo: str, caminho: str, corpo: dict | None = None, query: dict | None = None) -> dict:
    url = BASE + caminho
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": f"Bearer {_chave()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            texto = resp.read().decode() or "{}"
            return json.loads(texto)
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read().decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            erro = {}
        mensagem = erro.get("error") or erro.get("message") or f"Erro {e.code} na plataforma de publicação."
        if e.code == 409:
            mensagem = "Esse mesmo conteúdo já foi agendado ou publicado nessa conta nas últimas 24 horas."
        elif e.code == 401:
            mensagem = "A chave da plataforma de publicação é inválida. Avise o administrador."
        raise ErroPublicacao(mensagem) from None
    except urllib.error.URLError:
        raise ErroPublicacao("Não consegui falar com a plataforma de publicação agora. Tente de novo em alguns minutos.") from None


# ─── Perfis e contas ───

def criar_perfil(nome: str) -> str:
    r = _requisicao("POST", "/profiles", {"name": (nome or "Perfil")[:80]})
    return r["profile"]["_id"]


def link_conexao(profile_id: str, redirect_url: str) -> str:
    r = _requisicao("GET", "/connect/instagram", query={"profileId": profile_id, "redirect_url": redirect_url})
    return r["authUrl"]


def contas_instagram(profile_id: str) -> list:
    r = _requisicao("GET", "/accounts", query={"profileId": profile_id, "platform": "instagram"})
    return r.get("accounts") or []


def desconectar(account_id: str):
    try:
        _requisicao("DELETE", f"/accounts/{urllib.parse.quote(account_id)}")
    except ErroPublicacao:
        pass  # já desconectada, ou fora do ar: seguimos e limpamos do nosso lado


# ─── Mídia e posts ───

def enviar_imagem(conteudo: bytes, nome_arquivo: str, tipo: str = "image/png") -> str:
    """Sobe a imagem pro armazenamento do Zernio e devolve o publicUrl."""
    r = _requisicao("POST", "/media/presign", {"filename": nome_arquivo, "contentType": tipo, "size": len(conteudo)})
    req = urllib.request.Request(r["uploadUrl"], data=conteudo, method="PUT", headers={"Content-Type": tipo})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            pass
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise ErroPublicacao("Falha ao enviar as artes pra plataforma de publicação. Tente de novo.") from None
    return r["publicUrl"]


def criar_post(account_id: str, legenda: str, urls_imagens: list, quando: str | None, id_requisicao: str | None = None) -> dict:
    """quando=None publica agora; senão 'AAAA-MM-DDTHH:MM' no fuso de Brasília."""
    if not urls_imagens:
        raise ErroPublicacao("O Instagram exige pelo menos uma imagem no post.")
    corpo = {
        "content": (legenda or "")[:2200],
        "mediaItems": [{"type": "image", "url": u} for u in urls_imagens[:10]],
        "platforms": [{"platform": "instagram", "accountId": account_id}],
    }
    if quando:
        corpo.update({"scheduledFor": quando, "timezone": FUSO})
    else:
        corpo["publishNow"] = True
    url = BASE + "/posts"
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST", headers={
        "Authorization": f"Bearer {_chave()}", "Content-Type": "application/json", "Accept": "application/json",
        **({"x-request-id": id_requisicao} if id_requisicao else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return _resumo_post(json.loads(resp.read().decode() or "{}").get("post") or {})
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read().decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            erro = {}
        if e.code == 409:
            raise ErroPublicacao("Esse mesmo conteúdo já foi agendado ou publicado nessa conta nas últimas 24 horas.") from None
        raise ErroPublicacao(erro.get("error") or f"Erro {e.code} ao criar a publicação.") from None
    except urllib.error.URLError:
        raise ErroPublicacao("Não consegui falar com a plataforma de publicação agora. Tente de novo em alguns minutos.") from None


def ver_post(post_id: str) -> dict:
    r = _requisicao("GET", f"/posts/{urllib.parse.quote(post_id)}")
    return _resumo_post(r.get("post") or {})


def cancelar_post(post_id: str):
    _requisicao("DELETE", f"/posts/{urllib.parse.quote(post_id)}")


def _resumo_post(post: dict) -> dict:
    """Converte o status do Zernio pro nosso: agendado, publicando,
    publicado, erro."""
    plataformas = post.get("platforms") or [{}]
    p = plataformas[0] if plataformas else {}
    bruto = (post.get("status") or "").lower()
    status = {"scheduled": "agendado", "publishing": "publicando", "published": "publicado",
              "failed": "erro", "partial": "erro", "draft": "agendado", "cancelled": "cancelado"}.get(bruto, "publicando")
    erro = p.get("errorMessage") or p.get("error") or post.get("error")
    if isinstance(erro, dict):
        erro = erro.get("message") or json.dumps(erro)[:300]
    return {"id": post.get("_id"), "status": status, "url": p.get("platformPostUrl"), "erro": erro}
