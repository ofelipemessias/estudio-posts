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


def buscar_cep(cep: str) -> dict | None:
    """Endereço pelo CEP (ViaCEP, público e gratuito). None se não existir."""
    cep = so_digitos(cep)
    if len(cep) != 8:
        return None
    try:
        with urllib.request.urlopen(f"https://viacep.com.br/ws/{cep}/json/", timeout=15) as resp:
            d = json.loads(resp.read().decode() or "{}")
    except (urllib.error.URLError, ValueError):
        raise ErroPagamento("Não consegui consultar o CEP agora. Tente de novo em instantes.") from None
    if not d or d.get("erro"):
        return None
    return {"rua": d.get("logradouro") or "", "bairro": d.get("bairro") or "", "cidade": d.get("localidade") or "",
            "uf": d.get("uf") or "", "ibge": d.get("ibge") or ""}


def _dados_cadastro(telefone: str, endereco: dict) -> dict:
    """O checkout do cartão exige telefone e endereço no cadastro do cliente."""
    tel = so_digitos(telefone)
    return {
        "phone": tel, "mobilePhone": tel,
        "postalCode": so_digitos(endereco.get("cep")), "address": (endereco.get("rua") or "")[:120],
        "addressNumber": (endereco.get("numero") or "")[:20], "complement": (endereco.get("complemento") or "")[:100],
        "province": (endereco.get("bairro") or "")[:80],
    }


def criar_cliente(nome: str, email: str, cpf_cnpj: str, referencia: str, telefone: str, endereco: dict) -> str:
    r = _requisicao("POST", "/customers", {
        "name": (nome or "Cliente")[:100], "email": email, "cpfCnpj": so_digitos(cpf_cnpj),
        **_dados_cadastro(telefone, endereco),
        "externalReference": referencia, "notificationDisabled": False,
    })
    return r["id"]


def atualizar_cliente(customer_id: str, telefone: str, endereco: dict):
    _requisicao("POST", f"/customers/{urllib.parse.quote(customer_id)}", _dados_cadastro(telefone, endereco))


def ver_cliente(customer_id: str) -> dict:
    return _requisicao("GET", f"/customers/{urllib.parse.quote(customer_id)}")


def checkout_cartao(dados: dict, nome_plano: str, valor: float, urls: dict, referencia: str) -> dict:
    """Checkout recorrente no cartão, com os dados completos do pagador em
    customerData (o checkout exige telefone, endereço e o código IBGE da
    cidade). Devolve {"id", "url"}."""
    agora = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
    tel = so_digitos(dados.get("telefone"))
    cliente = {
        "name": (dados.get("nome") or "Cliente")[:100], "cpfCnpj": so_digitos(dados.get("cpf_cnpj")), "email": dados.get("email"),
        "phone": tel, "address": (dados.get("rua") or "")[:120], "addressNumber": (dados.get("numero") or "")[:20],
        "complement": (dados.get("complemento") or "")[:100], "province": (dados.get("bairro") or "")[:80],
        "postalCode": so_digitos(dados.get("cep")),
    }
    if str(dados.get("ibge") or "").isdigit():
        cliente["city"] = int(dados["ibge"])
    r = _requisicao("POST", "/checkouts", {
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": 60,
        "externalReference": referencia[:200],
        "callback": {"successUrl": urls["sucesso"], "cancelUrl": urls["cancelado"], "expiredUrl": urls["expirado"]},
        "items": [{"name": nome_plano[:60], "description": f"Assinatura mensal {nome_plano}"[:100], "quantity": 1, "value": round(valor, 2)}],
        "subscription": {"cycle": "MONTHLY", "nextDueDate": agora},
        "customerData": cliente,
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
