"""
emails.py — e-mails automáticos pelo Resend (https://resend.com).
Usa só a biblioteca padrão do Python. Sem RESEND_API_KEY, nada é enviado
(o sistema continua funcionando normalmente).

E-mails: convite, boas-vindas, lembrete do primeiro post, teste acabando e
teste encerrado. Todos com "responder" indo pro seu e-mail pessoal.
"""
import html
import json
import os
import urllib.error
import urllib.request


def configurado() -> bool:
    return bool(os.environ.get("RESEND_API_KEY", "").strip() and os.environ.get("EMAIL_REMETENTE", "").strip())


def enviar(para: str, assunto: str, corpo_html: str, corpo_texto: str) -> bool:
    """Envia um e-mail. Devolve True se o Resend aceitou."""
    if not configurado() or not para:
        return False
    dados = {
        "from": os.environ["EMAIL_REMETENTE"].strip(),
        "to": [para],
        "subject": assunto,
        "html": corpo_html,
        "text": corpo_texto,
    }
    responder = os.environ.get("EMAIL_RESPONDER_PARA", "").strip()
    if responder:
        dados["reply_to"] = responder
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(dados).encode(), method="POST",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}", "Content-Type": "application/json",
                 "User-Agent": "AdvogaMais/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


# ─── Modelos ───

def _assinatura() -> tuple[str, str]:
    nome = os.environ.get("EMAIL_ASSINATURA", "").strip() or os.environ.get("DONO_NOME", "").strip() or "Equipe"
    whats = "".join(c for c in os.environ.get("SUPORTE_WHATSAPP", "") if c.isdigit())
    linha_whats_txt = f"\nSe preferir, me chama no WhatsApp: https://wa.me/{whats}" if whats else ""
    linha_whats_html = (f'<p style="margin:0 0 6px;">Se preferir, me chama no WhatsApp: '
                        f'<a href="https://wa.me/{whats}" style="color:#1F6F5C;">clique aqui</a></p>') if whats else ""
    html_ = (f'<p style="margin:18px 0 6px;">Qualquer dúvida, é só responder este e-mail.</p>{linha_whats_html}'
             f'<p style="margin:14px 0 0;">{html.escape(nome)}</p>')
    txt = f"\n\nQualquer dúvida, é só responder este e-mail.{linha_whats_txt}\n\n{nome}"
    return html_, txt


def _montar(app_nome: str, titulo: str, paragrafos: list[str], botao: tuple[str, str] | None = None,
            lista: list[str] | None = None) -> tuple[str, str]:
    """Monta o HTML (com estilo inline, que funciona em qualquer leitor de e-mail) e o texto puro."""
    esc = html.escape
    ass_html, ass_txt = _assinatura()
    blocos = "".join(f'<p style="margin:0 0 12px;">{p}</p>' for p in paragrafos)
    itens = "".join(f'<li style="margin:0 0 6px;">{i}</li>' for i in (lista or []))
    lista_html = f'<ol style="margin:0 0 14px; padding-left:20px;">{itens}</ol>' if lista else ""
    botao_html = (f'<p style="margin:18px 0;"><a href="{esc(botao[1])}" style="background:#1F6F5C; color:#ffffff; '
                  f'text-decoration:none; padding:12px 20px; border-radius:8px; font-weight:bold; display:inline-block;">'
                  f'{esc(botao[0])}</a></p>') if botao else ""
    corpo = f"""<div style="background:#F5F4F0; padding:24px 12px; font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:14px; padding:28px; color:#14161B; font-size:15px; line-height:1.55;">
    <div style="font-size:20px; font-weight:bold; margin-bottom:18px;">{esc(app_nome)}</div>
    <h1 style="font-size:20px; margin:0 0 14px;">{esc(titulo)}</h1>
    {blocos}{lista_html}{botao_html}{ass_html}
  </div>
</div>"""
    # texto puro (sem tags)
    import re as _re
    limpa = lambda s: _re.sub(r"<[^>]+>", "", s)
    txt = titulo + "\n\n" + "\n\n".join(limpa(p) for p in paragrafos)
    if lista:
        txt += "\n\n" + "\n".join(f"{n}. {limpa(i)}" for n, i in enumerate(lista, 1))
    if botao:
        txt += f"\n\n{botao[0]}: {botao[1]}"
    return corpo, txt + ass_txt


def convite(app_nome: str, nome: str, link: str, dias: int | None) -> tuple[str, str, str]:
    primeiro = html.escape((nome or "").split(" ")[0] or "Olá")
    prazo = f" por {dias} dias" if dias else ""
    h, t = _montar(app_nome, f"Você foi convidado pro {app_nome}", [
        f"Olá, {primeiro}!",
        f"Liberei pra você o acesso ao {html.escape(app_nome)}{prazo}: ele cria posts pro Instagram de advogados, "
        "já no seu nicho, com arte, legenda e roteiro de Reels.",
        "É só criar sua senha e escolher sua área. Leva uns 2 minutos.",
    ], ("Criar minha senha", link))
    return f"Seu acesso ao {app_nome} está pronto", h, t


def boas_vindas(app_nome: str, nome: str, link: str) -> tuple[str, str, str]:
    primeiro = html.escape((nome or "").split(" ")[0] or "Olá")
    h, t = _montar(app_nome, f"Bem-vindo ao {app_nome}! 🎉", [
        f"Olá, {primeiro}! Que bom ter você por aqui.",
        "Como funciona:",
    ], ("Criar meu primeiro post", link), lista=[
        "Escolha o tema (ou uma das sugestões prontas)",
        "A IA cria a arte e a legenda, no seu nicho e na sua voz",
        "Revise, baixe ou poste direto do celular",
    ])
    h = h.replace("Como funciona:</p>", "Como funciona:</p>").replace(
        "</ol>", '</ol><p style="margin:0 0 12px;"><b>Dica:</b> na aba Perfil, cole 3 ou 4 legendas antigas suas no campo '
                 '"DNA de escrita". A IA passa a escrever com o seu jeito.</p>', 1)
    t = t.replace("\n\nCriar meu primeiro post", "\n\nDica: na aba Perfil, cole 3 ou 4 legendas antigas suas no campo "
                  "\"DNA de escrita\". A IA passa a escrever com o seu jeito.\n\nCriar meu primeiro post", 1)
    return f"Bem-vindo ao {app_nome}! 🎉", h, t


def lembrete_primeiro_post(app_nome: str, nome: str, link: str) -> tuple[str, str, str]:
    primeiro = html.escape((nome or "").split(" ")[0] or "Olá")
    h, t = _montar(app_nome, "Seu primeiro post leva 1 minuto", [
        f"Oi, {primeiro}! Vi que você ainda não criou seu primeiro post.",
        "Não precisa pensar no tema: na tela de criar post já tem sugestões prontas pra sua área. "
        "É clicar em uma, gerar e ver o resultado.",
    ], ("Criar meu primeiro post", link))
    return "Seu primeiro post leva 1 minuto", h, t


def teste_acabando(app_nome: str, nome: str, link: str, dias: int, oferta: str) -> tuple[str, str, str]:
    primeiro = html.escape((nome or "").split(" ")[0] or "Olá")
    quando = "amanhã" if dias <= 1 else f"em {dias} dias"
    h, t = _montar(app_nome, f"Seu teste termina {quando}", [
        f"Oi, {primeiro}! Passando pra avisar que seu teste do {html.escape(app_nome)} termina {quando}.",
        html.escape(oferta),
        "Seus perfis e posts ficam guardados. Assinando agora, você não perde nenhum dia de uso.",
    ], ("Ver os planos", link))
    return f"Seu teste termina {quando}", h, t


def teste_encerrado(app_nome: str, nome: str, link: str, oferta: str) -> tuple[str, str, str]:
    primeiro = html.escape((nome or "").split(" ")[0] or "Olá")
    h, t = _montar(app_nome, "Seu teste terminou", [
        f"Oi, {primeiro}! Seu período de teste do {html.escape(app_nome)} terminou.",
        "Seus perfis e posts continuam guardados: é só escolher um plano pra voltar a usar.",
        html.escape(oferta),
    ], ("Escolher meu plano", link))
    return "Seu teste terminou: seus posts estão guardados", h, t
