"""
gerar_post.py — cérebro do Estúdio de Posts.

NADA é fixo de um escritório: cada PERFIL (um advogado ou escritório
cliente) traz a própria área de atuação, os próprios temas ("frentes"),
o próprio público e o próprio DNA de escrita. As regras de publicidade
da OAB (Provimento 205/2021) valem pra todos.
"""
import json
import os
import re

import anthropic

MODELO = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

FORMATOS = {
    "carrossel": "Carrossel (vários slides)",
    "post_unico": "Post único (1 imagem estilo tweet)",
    "reels": "Roteiro de Reels (texto + capa)",
}

VOZES = {
    "eu": "Primeira pessoa (\"eu\"): é o próprio advogado falando",
    "nos": "Institucional (\"nós\"): é o escritório falando",
    "neutra": "Neutra: sem se colocar no texto",
}

INSTRUCOES_VOZ = {
    "eu": """VOZ: PRIMEIRA PESSOA ("EU") — OBRIGATÓRIO EM TUDO (slides, legenda e roteiro)
- Quem fala é o próprio advogado, em primeira pessoa: "eu vejo", "no meu dia a dia", "o que eu
  sempre digo", "já acompanhei muitos casos assim" (sem identificar clientes).
- Pelo menos o slide de gancho, um slide do meio e o slide final precisam ter a primeira pessoa.
- Tom de conversa próxima, como se estivesse explicando pra alguém na frente dele.
- Nunca fale como "nós, o escritório".""",
    "nos": """VOZ: INSTITUCIONAL ("NÓS") — OBRIGATÓRIO EM TUDO (slides, legenda e roteiro)
- Quem fala é o escritório, na primeira pessoa do plural: "nós vemos", "aqui no escritório",
  "o que orientamos". Nunca use "eu".
- Tom de marca: objetivo, seguro, prático, organizado em passos e checklists.""",
    "neutra": """VOZ: NEUTRA
- Não use "eu" nem "nós". Fale diretamente com o leitor ("você").""",
}

ESTILOS_ESCRITA = {
    "educativo": "Educativo: explica com clareza, passo a passo, tom acolhedor e seguro.",
    "equilibrado": "Equilibrado: informativo, mas com frases de impacto e posicionamento firme.",
    "autoridade": "Autoridade: tom técnico e confiante, mostra domínio do assunto sem juridiquês.",
    "direto": "Direto: frases curtas, sem rodeio, vai ao ponto na primeira linha.",
}

# ---------------------------------------------------------------------------
# Modelos prontos pra acelerar o cadastro de um perfil novo. Tudo é
# editável depois, na aba "Perfil".
# ---------------------------------------------------------------------------

MODELOS_PERFIL = {
    "digital_consumidor": {
        "rotulo": "Direito Digital, Consumidor e Bancário",
        "area": "Direito Digital, do Consumidor e Bancário",
        "frentes": [
            {"nome": "Contas", "descricao": "Recuperação de contas (Instagram, WhatsApp, Facebook) hackeadas, banidas ou desativadas"},
            {"nome": "Golpes e Pix", "descricao": "Golpes e fraudes digitais: Pix, falso atendente, perfil clonado, links falsos"},
            {"nome": "Bancário", "descricao": "Banco que nega devolução, falha de segurança, MED do Pix, empréstimo não reconhecido"},
            {"nome": "Consumidor", "descricao": "Cobrança indevida, produto ou serviço com defeito, negativação indevida"},
        ],
        "publico": """QUEM É O PÚBLICO
- Pequenos empreendedores que vendem pelo Instagram/WhatsApp e perdem a conta, e com ela o faturamento.
- Pessoas que caíram em golpe (Pix, falso atendente, perfil clonado) e ouviram do banco que "a culpa é sua".
- Consumidores lesados que acham que "não adianta reclamar".

O QUE ELES SENTEM (e quase nunca falam)
- Vergonha de ter caído no golpe; desespero de perder o negócio; impotência diante de suporte automático.
- Crença errada de que "perdeu a conta, já era" ou "Pix não tem volta".

OS "INIMIGOS" DO PÚBLICO
- Suporte de plataforma que só manda resposta automática.
- Banco que culpa o cliente e se recusa a devolver.
- Golpistas; robôs que banem sem explicação; empresas que contam com o cansaço do consumidor.""",
    },
    "previdenciario": {
        "rotulo": "Previdenciário",
        "area": "Direito Previdenciário",
        "frentes": [
            {"nome": "Aposentadoria", "descricao": "Regras de aposentadoria, tempo de contribuição, revisão de benefício"},
            {"nome": "Benefícios por incapacidade", "descricao": "Auxílio por incapacidade, perícia do INSS, benefício negado"},
            {"nome": "BPC/LOAS", "descricao": "Benefício assistencial para idosos e pessoas com deficiência"},
            {"nome": "Maternidade e família", "descricao": "Salário-maternidade, pensão por morte"},
        ],
        "publico": """QUEM É O PÚBLICO
- Trabalhadores perto de se aposentar, com medo de perder direitos ou de fazer errado.
- Pessoas doentes ou incapacitadas que tiveram benefício negado ou cortado.
- Famílias de baixa renda com idosos ou pessoas com deficiência.

O QUE ELES SENTEM
- Medo da burocracia e da perícia; sensação de humilhação no atendimento; insegurança financeira.

OS "INIMIGOS" DO PÚBLICO
- Burocracia do INSS; perícia que não olha o caso real; desinformação; filas e prazos sem fim.""",
    },
    "trabalhista": {
        "rotulo": "Trabalhista",
        "area": "Direito do Trabalho",
        "frentes": [
            {"nome": "Rescisão", "descricao": "Verbas rescisórias, demissão, justa causa, acordo"},
            {"nome": "Jornada", "descricao": "Horas extras, banco de horas, escala, intervalo"},
            {"nome": "Assédio e saúde", "descricao": "Assédio moral, doença ocupacional, acidente de trabalho"},
            {"nome": "Empresas", "descricao": "Prevenção de passivo trabalhista para empregadores"},
        ],
        "publico": """QUEM É O PÚBLICO
- Trabalhadores com dúvida sobre direitos na demissão ou na rotina de trabalho.
- Pequenos empresários que querem evitar processo trabalhista.

O QUE ELES SENTEM
- Medo de perder o emprego ao reclamar; sensação de injustiça; empresário com medo de "passivo escondido".

OS "INIMIGOS" DO PÚBLICO
- Empresa que não paga o que deve; informalidade; desinformação; "jeitinho" que vira prova contra.""",
    },
    "familia": {
        "rotulo": "Família e Sucessões",
        "area": "Direito de Família e Sucessões",
        "frentes": [
            {"nome": "Divórcio", "descricao": "Divórcio, partilha de bens, união estável"},
            {"nome": "Filhos", "descricao": "Guarda, convivência, pensão alimentícia"},
            {"nome": "Inventário", "descricao": "Inventário, herança, testamento, planejamento sucessório"},
        ],
        "publico": """QUEM É O PÚBLICO
- Pessoas passando por separação, preocupadas com filhos e patrimônio.
- Famílias lidando com a perda de alguém e com a herança.

O QUE ELES SENTEM
- Dor emocional, medo de conflito, insegurança sobre o futuro dos filhos, receio de brigas na família.

OS "INIMIGOS" DO PÚBLICO
- Desinformação; decisões tomadas no calor da emoção; demora e custo de inventário mal planejado.""",
    },
    "em_branco": {
        "rotulo": "Outra área (em branco)",
        "area": "",
        "frentes": [{"nome": "Geral", "descricao": "Temas gerais da área de atuação"}],
        "publico": "QUEM É O PÚBLICO\n- \n\nO QUE ELES SENTEM\n- \n\nOS \"INIMIGOS\" DO PÚBLICO\n- ",
    },
}

REGRAS_OAB = """REGRAS DE PUBLICIDADE DA ADVOCACIA (Provimento 205/2021 do CFOAB) — OBRIGATÓRIAS
- Conteúdo informativo e educativo em primeiro lugar. Nada de tom de anúncio.
- PROIBIDO: prometer resultado, citar preços, honorários ou gratuidade, "contrate-nos", "ligue já",
  comparação com outros advogados, sensacionalismo, depoimento ou caso de cliente identificável,
  dados de processos.
- CTA permitido: convidar a salvar, compartilhar, seguir o perfil, comentar uma dúvida, ou
  "fale com um advogado de confiança". Mencionar o advogado/escritório só de forma sóbria.
- Não afirme dado jurídico que você não tem certeza (número de lei, prazo exato, decisão). Na
  dúvida, deixe genérico ("a Justiça tem entendido que...").
- Nunca insinue indenização como certa ou vantajosa ("pode ser cobrado da empresa", "você pode
  ganhar", "muito mais do que isso"). Use sempre: "pode, dependendo do caso, gerar direito à
  reparação".
- Não use travessão (— ou –) em nenhum texto: nem nos slides, nem na legenda, nem no roteiro.
- Nada de política partidária."""

REGRAS_FORMATO = {
    "carrossel": """FORMATO: CARROSSEL de {n_slides} slides, estrutura AIDA
- Slide 1 = gancho que para o scroll (contradiz uma crença, provoca, ou fala da dor na cara).
- Slides do meio = problema e depois o conteúdo de valor (o que fazer, direitos, erros comuns).
- Último slide = fechamento com CTA permitido pelas regras da OAB.
- Cada slide: no máximo ~45 palavras, frases curtas (até 12 palavras), parágrafos separados por
  linha em branco. Sem emoji, sem hashtag, sem travessão (— ou –), sem numeração "1/10".
- Pode destacar 1 a 3 palavras-chave por slide com **asterisco duplo**.""",
    "post_unico": """FORMATO: POST ÚNICO (uma imagem só, estilo tweet)
- Um texto só, de 25 a 60 palavras, com começo forte e uma virada no final.
- Parágrafos curtos separados por linha em branco. Sem emoji, sem hashtag, sem travessão.
- Pode destacar 1 a 3 palavras-chave com **asterisco duplo**.
- Devolva esse texto como o ÚNICO item da lista "slides".""",
    "reels": """FORMATO: ROTEIRO DE REELS (30 a 60 segundos, falado pelo advogado olhando pra câmera)
- Gancho nos 3 primeiros segundos.
- Cenas curtas com o que é falado e o texto que aparece na tela.
- Fechamento com CTA permitido pela OAB.
- Em "slides", devolva UM item só: a frase da CAPA do Reels (até 15 palavras, pode usar
  **destaque**).""",
}

SAIDA_JSON_POST = """SAÍDA — responda SOMENTE com um JSON válido (sem texto antes ou depois, sem ```), assim:
{
  "titulo_interno": "resumo do post em até 8 palavras, só pra organizar o histórico",
  "slides": ["texto do slide 1", "texto do slide 2", "..."],
  "roteiro_reels": null,
  "legenda": "legenda pronta pro Instagram (3 a 6 parágrafos curtos, pode ter 1 ou 2 emojis, termina com o CTA)",
  "hashtags": ["#exemplo", "... de 5 a 10, específicas do tema"],
  "alertas": ["pontos que um advogado precisa conferir antes de publicar (afirmações jurídicas, regra da OAB, dado da notícia). Lista vazia se não houver."]
}
Para Reels, "roteiro_reels" deve ser:
{"gancho": "...", "cenas": [{"tempo": "0-3s", "fala": "...", "na_tela": "..."}], "fechamento": "..."}"""

SAIDA_JSON_PAUTAS = """SAÍDA — responda SOMENTE com um JSON válido (sem texto antes ou depois, sem ```):
{
  "pautas": [
    {
      "titulo": "título curto da pauta",
      "resumo": "2 frases explicando o fato ou a situação",
      "por_que_importa": "por que isso mexe com o público",
      "angulo": "a frase-gancho sugerida pro post",
      "frente": "o NOME exato de uma das frentes listadas",
      "formato_sugerido": "carrossel | post_unico | reels",
      "potencial": "alto | medio",
      "fonte_nome": "nome do veículo (vazio se for ideia sem notícia)",
      "fonte_url": "link da matéria (vazio se for ideia sem notícia)",
      "data": "data da notícia, se houver"
    }
  ]
}"""


def _cliente():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada (veja o arquivo .env).")
    return anthropic.Anthropic(api_key=api_key)


def extrair_uso(resposta) -> dict:
    """Tokens e buscas de uma chamada, pra calcular o custo por cliente."""
    u = getattr(resposta, "usage", None)
    servidor = getattr(u, "server_tool_use", None) if u else None
    return {
        "entrada": int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0)
                   + int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        "saida": int(getattr(u, "output_tokens", 0) or 0),
        "buscas": int(getattr(servidor, "web_search_requests", 0) or 0) if servidor else 0,
    }


def _ultimo_texto(resposta) -> str:
    blocos = [b.text for b in resposta.content if getattr(b, "type", None) == "text"]
    return blocos[-1].strip() if blocos else ""


def _extrair_json(texto: str) -> dict:
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fim == -1:
            raise RuntimeError("A IA não devolveu um JSON válido.")
        return json.loads(texto[inicio:fim + 1])


def _sem_travessao(texto: str) -> str:
    return re.sub(r"\s*[—–]\s*", ", ", texto or "").strip()


def _limpar_roteiro(roteiro):
    if not isinstance(roteiro, dict):
        return None
    limpo = {k: _sem_travessao(str(roteiro.get(k) or "")) for k in ("gancho", "fechamento")}
    limpo["cenas"] = [
        {"tempo": str(c.get("tempo") or ""), "fala": _sem_travessao(str(c.get("fala") or "")),
         "na_tela": _sem_travessao(str(c.get("na_tela") or ""))}
        for c in (roteiro.get("cenas") or []) if isinstance(c, dict)
    ]
    return limpo


def _limpar_slide(texto: str) -> str:
    texto = re.sub(r"\s*[—–]\s*", ", ", texto or "")
    texto = re.sub(r"^\s*\d+\s*/\s*\d+\s*", "", texto)
    return texto.strip()


def _bloco_perfil(perfil: dict) -> str:
    partes = [
        "SOBRE QUEM ASSINA O CONTEÚDO",
        f"- Nome: {perfil.get('nome_exibicao') or ''}",
        f"- Área de atuação: {perfil.get('area') or 'não informada'}",
    ]
    if (perfil.get("sobre") or "").strip():
        partes.append(f"- Contexto: {perfil['sobre'].strip()}")
    partes.append("O \"inimigo\" do conteúdo é sempre o problema, a empresa ou a situação que prejudica o público, nunca o próprio leitor.")
    return "\n".join(partes)


def _bloco_dna(perfil: dict) -> str:
    dna = (perfil.get("dna") or "").strip()
    if not dna:
        return ""
    return (
        "JEITO DE ESCREVER (DNA)\n"
        "Abaixo estão posts que essa pessoa já publicou. Imite o vocabulário, o ritmo das frases e o "
        "tom, sem copiar trechos:\n"
        f"<<<\n{dna[:6000]}\n>>>"
    )


def _descricao_frente(perfil: dict, nome_frente: str) -> str:
    for f in perfil.get("frentes") or []:
        if f.get("nome") == nome_frente:
            return f"{f['nome']}: {f.get('descricao', '')}"
    return nome_frente or "Geral"


def gerar_post(opcoes: dict, perfil: dict) -> dict:
    formato = opcoes["formato"]
    n_slides = max(4, min(12, int(opcoes.get("n_slides") or 7)))

    system = "\n\n".join(p for p in [
        "Você é o redator de redes sociais de um advogado. Escreve em português do Brasil, linguagem "
        "simples, sem juridiquês, pra quem não é da área.",
        _bloco_perfil(perfil),
        (perfil.get("publico") or "").strip(),
        _bloco_dna(perfil),
        REGRAS_OAB,
        INSTRUCOES_VOZ.get(perfil.get("voz") or "neutra", INSTRUCOES_VOZ["neutra"]),
        "TOM\n" + ESTILOS_ESCRITA.get(opcoes.get("estilo_escrita"), ESTILOS_ESCRITA["educativo"]),
        REGRAS_FORMATO[formato].format(n_slides=n_slides),
        SAIDA_JSON_POST,
    ] if p)

    pedido = [f"TEMA DA ÁREA (frente): {_descricao_frente(perfil, opcoes.get('frente'))}"]
    if opcoes.get("tema"):
        pedido.append(f"TEMA DO POST: {opcoes['tema']}")
    if any(opcoes.get(k) for k in ("pele_quem", "pele_momento", "pele_observacao")):
        pedido.append(
            "NA PELE DO CLIENTE (situação real, sem identificar ninguém):\n"
            f"- Quem é: {opcoes.get('pele_quem') or '-'}\n"
            f"- Momento que está vivendo: {opcoes.get('pele_momento') or '-'}\n"
            f"- O que o advogado já observou nesses casos: {opcoes.get('pele_observacao') or '-'}\n"
            "Escreva de forma que essa pessoa se reconheça no post."
        )
    noticia = opcoes.get("noticia") or None
    if noticia:
        pedido.append(
            "BASE: NOTÍCIA REAL (use só o que está aqui, não invente detalhes):\n"
            f"- Título: {noticia.get('titulo', '')}\n- Resumo: {noticia.get('resumo', '')}\n"
            f"- Fonte: {noticia.get('fonte_nome', '')} {noticia.get('fonte_url', '')}\n"
            f"- Ângulo sugerido: {noticia.get('angulo', '')}\n"
            "Cite a fonte na legenda."
        )
    if opcoes.get("cta"):
        pedido.append(f"CTA DESEJADO (ajuste se ferir a regra da OAB): {opcoes['cta']}")
    pedido.append("Escreva o post agora.")

    resposta = _cliente().messages.create(
        model=MODELO, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": "\n\n".join(pedido)}],
    )
    dados = _extrair_json(_ultimo_texto(resposta))
    dados["_uso"] = extrair_uso(resposta)

    slides = [_limpar_slide(s) for s in (dados.get("slides") or []) if str(s).strip()]
    if not slides:
        raise RuntimeError("A IA não devolveu o texto dos slides.")
    if formato in ("post_unico", "reels"):
        slides = slides[:1]
    dados["slides"] = slides
    dados["hashtags"] = [h if h.startswith("#") else "#" + h for h in (dados.get("hashtags") or [])][:12]
    dados["alertas"] = dados.get("alertas") or []
    dados["legenda"] = _sem_travessao(dados.get("legenda") or "")
    dados["roteiro_reels"] = _limpar_roteiro(dados.get("roteiro_reels")) if formato == "reels" else None
    return dados


def buscar_pautas(modo: str, frentes_escolhidas: list, perfil: dict, periodo_dias: int = 7) -> list:
    todas = perfil.get("frentes") or [{"nome": "Geral", "descricao": ""}]
    nomes_validos = [f["nome"] for f in todas]
    frentes = [f for f in todas if f["nome"] in frentes_escolhidas] or todas
    lista_frentes = "\n".join(f"- {f['nome']}: {f.get('descricao', '')}" for f in frentes)

    if modo == "noticias":
        instrucao = f"""TAREFA: encontre de 6 a 8 NOTÍCIAS REAIS publicadas nos últimos {periodo_dias} dias no Brasil
que rendam posts pro Instagram desse advogado, SÓ dentro destes temas:
{lista_frentes}

Busque: mudanças de lei ou de regra, decisões relevantes da Justiça, alertas de órgãos públicos,
casos que viralizaram, novidades que afetam o dia a dia do público descrito.

Use a ferramenta de busca de verdade. Só inclua notícias que você encontrou, com o link real.
Confira a data. Ignore política partidária e o que não tiver relação com os temas acima.
Na resposta final, NÃO narre a pesquisa: devolva só o JSON."""
    else:
        instrucao = f"""TAREFA: sugira 8 pautas ATEMPORAIS (que funcionam em qualquer semana) pro Instagram desse
advogado, dentro destes temas:
{lista_frentes}

Parta das dores, crenças erradas e "inimigos" do público descritos acima. Varie os formatos
e os ganchos (erro comum, mito x verdade, passo a passo, "o que ninguém te conta", checklist).
Deixe fonte_nome, fonte_url e data vazios."""

    system = "\n\n".join(p for p in [
        "Você é o estrategista de conteúdo de um advogado no Instagram.",
        _bloco_perfil(perfil),
        (perfil.get("publico") or "").strip(),
        REGRAS_OAB,
        SAIDA_JSON_PAUTAS,
    ] if p)
    kwargs = dict(model=MODELO, max_tokens=6000, system=system, messages=[{"role": "user", "content": instrucao}])
    if modo == "noticias":
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]

    resposta = _cliente().messages.create(**kwargs)
    dados = _extrair_json(_ultimo_texto(resposta))
    pautas = dados.get("pautas") or []
    for p in pautas:
        if p.get("frente") not in nomes_validos:
            p["frente"] = frentes[0]["nome"]
        if p.get("formato_sugerido") not in FORMATOS:
            p["formato_sugerido"] = "carrossel"
    return pautas, extrair_uso(resposta)


def texto_legenda_completa(dados: dict) -> str:
    legenda = dados.get("legenda") or ""
    hashtags = " ".join(dados.get("hashtags") or [])
    return (legenda + ("\n\n" + hashtags if hashtags else "")).strip()


def texto_roteiro(roteiro: dict | None) -> str:
    if not roteiro:
        return ""
    linhas = [f"GANCHO: {roteiro.get('gancho', '')}", ""]
    for c in roteiro.get("cenas") or []:
        linhas.append(f"[{c.get('tempo', '')}]")
        linhas.append(f"Fala: {c.get('fala', '')}")
        if c.get("na_tela"):
            linhas.append(f"Na tela: {c['na_tela']}")
        linhas.append("")
    linhas.append(f"FECHAMENTO: {roteiro.get('fechamento', '')}")
    return "\n".join(linhas).strip()
