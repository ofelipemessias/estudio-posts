"""
pagamentos.py — cobrança das assinaturas pelo Asaas (https://docs.asaas.com).
Usa só a biblioteca padrão do Python.

- CARTÃO: Asaas Checkout recorrente (chargeTypes=RECURRENT). O cliente
  digita o cartão na página segura do Asaas (o sistema nunca vê os dados
  do cartão) e as próximas mensalidades são cobradas automaticamente.
- PIX: assinatura mensal comum (billingType=PIX); o Asaas gera e envia a
  cobrança Pix todo mês.
- Cada pessoa vira um "customer" no Asaas; todo pagamento que chega pelo
  webhook traz esse id, e é assim que o sistema sabe de quem é.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TIMEOUT = 60
FUSO_BR = timezone(timedelta(hours=-3))


class ErroPagamento(Exception):
    """Erro com mensagem pronta pra mostrar pro usuário."""


def ambiente() -> str:
    return "producao" if os.environ.get("ASAAS_AMBIENTE", "sandbox").strip().lower() in ("producao", "produção", "production") else "sandbox"


def base_api() -> str:
    return "https://api.asaas.com/v3" if ambiente() == "producao" else "https://api-sandbox.asaas.com/v3"


def base_checkout() -> str:
    return "https://asaas.com/checkoutSession/show?id=" if ambiente() == "producao" else "https://sandbox.asaas.com/checkoutSession/show?id="


def configurado() -> bool:
    return bool(os.environ.get("ASAAS_API_KEY", "").strip())


def _chave() -> str:
    chave = os.environ.get("ASAAS_API_KEY", "").strip()
    if not chave:
        raise ErroPagamento("O pagamento ainda não foi configurado no servidor.")
    return chave


def _requisicao(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    req = urllib.request.Request(
        base_api() + caminho,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        method=metodo,
        headers={"access_token": _chave(), "Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "AdvogaMais/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read().decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            erro = {}
        erros = erro.get("errors") or []
        mensagem = erros[0].get("description") if erros and isinstance(erros[0], dict) else None
        if e.code == 401:
            mensagem = "A chave do Asaas é inválida. Avise o administrador."
        raise ErroPagamento(mensagem or f"Erro {e.code} no Asaas.") from None
    except urllib.error.URLError:
        raise ErroPagamento("Não consegui falar com o Asaas agora. Tente de novo em alguns minutos.") from None


def so_digitos(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def criar_cliente(nome: str, email: str, cpf_cnpj: str, referencia: str, telefone: str) -> str:
    tel = so_digitos(telefone)
    r = _requisicao("POST", "/customers", {
        "name": (nome or "Cliente")[:100], "email": email, "cpfCnpj": so_digitos(cpf_cnpj),
        "phone": tel, "mobilePhone": tel,  # o checkout do cartão exige telefone
        "externalReference": referencia, "notificationDisabled": False,
    })
    return r["id"]


def atualizar_telefone(customer_id: str, telefone: str):
    tel = so_digitos(telefone)
    _requisicao("POST", f"/customers/{urllib.parse.quote(customer_id)}", {"phone": tel, "mobilePhone": tel})


def checkout_cartao(customer_id: str, nome_plano: str, valor: float, urls: dict) -> dict:
    """Checkout recorrente no cartão. Devolve {"id", "url"}."""
    agora = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
    r = _requisicao("POST", "/checkouts", {
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": 60,
        "callback": {"successUrl": urls["sucesso"], "cancelUrl": urls["cancelado"], "expiredUrl": urls["expirado"]},
        "items": [{"name": nome_plano[:60], "description": f"Assinatura mensal {nome_plano}"[:100], "quantity": 1, "value": round(valor, 2)}],
        "subscription": {"cycle": "MONTHLY", "nextDueDate": agora},
        "customer": customer_id,
    })
    return {"id": r["id"], "url": base_checkout() + urllib.parse.quote(r["id"])}


def assinatura_pix(customer_id: str, nome_plano: str, valor: float, referencia: str) -> dict:
    """Assinatura mensal no Pix. Devolve {"id", "url"} (url = fatura do 1º mês)."""
    hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
    r = _requisicao("POST", "/subscriptions", {
        "customer": customer_id, "billingType": "PIX", "value": round(valor, 2), "nextDueDate": hoje,
        "cycle": "MONTHLY", "description": f"Assinatura mensal {nome_plano}"[:100], "externalReference": referencia,
    })
    cobrancas = _requisicao("GET", f"/subscriptions/{urllib.parse.quote(r['id'])}/payments")
    lista = cobrancas.get("data") or []
    if not lista:
        raise ErroPagamento("A assinatura foi criada, mas a cobrança do primeiro mês ainda não apareceu. Tente de novo em instantes.")
    return {"id": r["id"], "url": lista[0].get("invoiceUrl")}


def cancelar_assinatura(subscription_id: str):
    try:
        _requisicao("DELETE", f"/subscriptions/{urllib.parse.quote(subscription_id)}")
    except ErroPagamento:
        pass  # já removida: seguimos e marcamos como cancelada do nosso lado
