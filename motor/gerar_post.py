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
    "post_unico": "Post único (1 imagem)",
    "story": "Stories (telas verticais)",
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
    "tributario": {
        "rotulo": "Tributário",
        "area": "Direito Tributário",
        "frentes": [
            {"nome": "Empresas", "descricao": "Planejamento tributário, regime de tributação, recuperação de créditos"},
            {"nome": "Pessoa física", "descricao": "Imposto de renda, malha fina, isenções (ex.: doença grave), herança e ITCMD"},
            {"nome": "Dívidas e execução", "descricao": "Dívida ativa, execução fiscal, parcelamentos e transação tributária"},
        ],
        "publico": """QUEM É O PÚBLICO
- Donos de pequenas e médias empresas que sentem que pagam imposto demais.
- Pessoas físicas com dúvida no imposto de renda, caídas na malha fina ou com dívida com a Receita.

O QUE ELES SENTEM
- Medo da Receita e de multas; sensação de pagar muito sem entender por quê; insegurança com mudanças de regra.

OS "INIMIGOS" DO PÚBLICO
- Burocracia fiscal; regras que mudam o tempo todo; cobrança automática sem análise; falta de orientação na hora certa.""",
    },
    "empresarial": {
        "rotulo": "Empresarial",
        "area": "Direito Empresarial",
        "frentes": [
            {"nome": "Sociedade", "descricao": "Contrato social, acordo de sócios, entrada e saída de sócios"},
            {"nome": "Contratos", "descricao": "Contratos com clientes, fornecedores e parceiros; cobrança e inadimplência"},
            {"nome": "Proteção do negócio", "descricao": "Marca, LGPD, prevenção de riscos e de processos"},
        ],
        "publico": """QUEM É O PÚBLICO
- Empreendedores e donos de pequenas empresas, sócios de negócios familiares e startups.

O QUE ELES SENTEM
- Pressa pra crescer e medo de "problema jurídico escondido"; insegurança com sócios, contratos e cópia da marca.

OS "INIMIGOS" DO PÚBLICO
- Contrato de modelo pronto da internet; sociedade só "no fio do bigode"; cliente que não paga; concorrente que copia.""",
    },
    "criminal": {
        "rotulo": "Criminal",
        "area": "Direito Penal e Processual Penal",
        "frentes": [
            {"nome": "Direitos na abordagem", "descricao": "Direitos na abordagem policial, prisão em flagrante, audiência de custódia"},
            {"nome": "Investigação e processo", "descricao": "Inquérito, depoimento, defesa, recursos"},
            {"nome": "Crimes digitais", "descricao": "Golpes, crimes contra a honra na internet, vazamento de conteúdo íntimo"},
        ],
        "publico": """QUEM É O PÚBLICO
- Pessoas (e familiares) que passam por uma investigação, abordagem ou processo criminal.
- Vítimas de crimes, inclusive digitais, que não sabem como agir.

O QUE ELES SENTEM
- Medo, urgência, vergonha e desinformação; sensação de estar sem saída.

OS "INIMIGOS" DO PÚBLICO
- Desinformação e boatos; agir sem orientação no primeiro momento; exposição nas redes.""",
    },
    "imobiliario": {
        "rotulo": "Imobiliário",
        "area": "Direito Imobiliário",
        "frentes": [
            {"nome": "Compra e venda", "descricao": "Contrato, documentação, financiamento, distrato"},
            {"nome": "Locação", "descricao": "Aluguel, despejo, reajuste, garantias"},
            {"nome": "Regularização", "descricao": "Usucapião, escritura, inventário de imóvel, condomínio"},
        ],
        "publico": """QUEM É O PÚBLICO
- Pessoas comprando, vendendo ou alugando imóvel; proprietários e inquilinos; famílias com imóvel irregular.

O QUE ELES SENTEM
- Medo de perder o dinheiro de uma vida; insegurança com contrato e documentação; cansaço com problema de condomínio.

OS "INIMIGOS" DO PÚBLICO
- Contrato mal feito; documentação irregular; construtora que atrasa; inquilino ou proprietário que não cumpre o combinado.""",
    },
    "saude": {
        "rotulo": "Saúde e Plano de Saúde",
        "area": "Direito à Saúde",
        "frentes": [
            {"nome": "Plano de saúde", "descricao": "Negativa de cobertura, reajuste abusivo, cancelamento do plano"},
            {"nome": "SUS e medicamentos", "descricao": "Medicamentos de alto custo, cirurgias, tratamentos pelo SUS"},
            {"nome": "Erro médico", "descricao": "Falhas no atendimento e direitos do paciente"},
        ],
        "publico": """QUEM É O PÚBLICO
- Pacientes e familiares que tiveram tratamento, exame ou remédio negado; idosos com reajuste alto do plano.

O QUE ELES SENTEM
- Urgência e angústia (a saúde não espera); impotência diante do plano ou do sistema.

OS "INIMIGOS" DO PÚBLICO
- Plano que nega cobertura; reajuste abusivo; burocracia e demora no SUS.""",
    },
    "em_branco": {
        "rotulo": "Outra área (a IA monta pra você)",
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

REGRAS_GERAIS = """REGRAS DE COMUNICAÇÃO (este perfil optou por NÃO seguir as regras de publicidade da OAB)
- Linguagem livre e persuasiva; pode convidar pra conhecer o serviço, chamar no direct, no WhatsApp ou
  no link da bio.
- Mesmo assim, SEMPRE: não invente dados, números, fontes, leis ou decisões (na dúvida, deixe genérico
  e aponte nos alertas); não faça promessa que não pode ser garantida (resultado certo, prazo
  garantido); não exponha pessoas identificáveis; nada de informação enganosa.
- Não use travessão (— ou –) em nenhum texto: nem nos slides, nem na legenda, nem no roteiro.
- Nada de política partidária."""


def segue_oab(perfil: dict | None) -> bool:
    """Regras de publicidade da OAB: ligadas por padrão; cada perfil pode desligar."""
    v = (perfil or {}).get("regras_oab")
    return True if v is None else bool(v)


REGRAS_FORMATO = {
    "carrossel": """FORMATO: CARROSSEL de {n_slides} slides, estrutura AIDA
- Slide 1 = gancho que para o scroll (contradiz uma crença, provoca, ou fala da dor na cara).
- Slides do meio = problema e depois o conteúdo de valor (o que fazer, direitos, erros comuns).
- Último slide = fechamento com {cta_regra}.
- NÃO use emoji nem símbolos como ✅ ❌ 👇 nos slides (a arte não exibe emoji); pra listas, use "- item".
  Na legenda, emoji é permitido com moderação. Hashtags sempre em minúsculas e sem acento.
- NÃO escreva "Slide 1", "1/7" ou qualquer numeração do slide no texto. NÃO quebre linha no meio
  de uma frase: cada parágrafo é uma linha só; use linha em branco entre parágrafos.
- Cada slide: no máximo ~45 palavras, frases curtas (até 12 palavras), parágrafos separados por
  linha em branco. Sem emoji, sem hashtag, sem travessão (— ou –), sem numeração "1/10".
- Pode destacar 1 a 3 palavras-chave por slide com **asterisco duplo**.""",
    "post_unico": """FORMATO: POST ÚNICO (uma imagem só, estilo tweet)
- Um texto só, de 25 a 60 palavras, com começo forte e uma virada no final.
- Parágrafos curtos separados por linha em branco. Sem emoji, sem hashtag, sem travessão.
- Pode destacar 1 a 3 palavras-chave com **asterisco duplo**.
- Devolva esse texto como o ÚNICO item da lista "slides".""",
    "story": """FORMATO: STORIES (sequência de 3 a 5 telas verticais, vistas rapidinho no celular)
- Cada tela: UMA ideia só, no máximo 25 palavras, frases bem curtas.
- Tela 1 = gancho que faz a pessoa tocar pra ver a próxima (pergunta ou afirmação forte).
- Telas do meio = a informação, em passos curtos.
- Última tela = {cta_regra} (ex.: responder a enquete ou a caixinha de perguntas, mandar a dúvida, salvar).
- Pode destacar 1 ou 2 palavras por tela com **asterisco duplo**.
- Sem emoji e sem símbolos como ✅ ❌ 👇 nas telas (a arte não exibe emoji). Pra listas, use "- item".
- Cada tela é um item da lista "slides". Na "legenda", escreva uma versão curta pra quem quiser
  repostar no feed (stories não têm legenda).""",
    "reels": """FORMATO: ROTEIRO DE REELS (30 a 60 segundos, falado pelo advogado olhando pra câmera)
- Gancho nos 3 primeiros segundos.
- Cenas curtas com o que é falado e o texto que aparece na tela.
- Fechamento com {cta_regra}.
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
      "formato_sugerido": "carrossel | post_unico | story | reels",
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


_ITEM_DE_LISTA = re.compile(r"^\s*([-•▪►✅✔☑❌⚠➡👉]|\d+[.)]\s)")


def _limpar_hashtags(lista) -> list:
    """Hashtags em minúsculas, sem acento nem espaço (é como as pessoas buscam)."""
    import unicodedata
    saida = []
    for h in lista:
        h = unicodedata.normalize("NFKD", str(h)).encode("ascii", "ignore").decode().lower()
        h = re.sub(r"[^a-z0-9_]", "", h)
        if h and "#" + h not in saida:
            saida.append("#" + h)
    return saida[:12]


def _limpar_slide(texto: str) -> str:
    """Limpa o texto de um slide gerado pela IA (não mexe em edições manuais):
    tira travessões, numeração ("1/7", "Slide 3:") e quebras de linha no meio
    de frase, que deixavam a arte com "degraus"."""
    texto = re.sub(r"\s*[—–]\s*", ", ", (texto or "").replace("\r", ""))
    texto = re.sub(r"^\s*\d+\s*/\s*\d+\s*", "", texto)
    # "Slide 3", "Slide 3:", "**Slide 3**" ou "**Slide 3:**" no começo (sem comer o ** de um destaque logo depois)
    texto = re.sub(r"^\s*(?:\*\*\s*(?:slide|card|tela|página)\s*\d+\s*[:.)\-]?\s*\*\*|(?:slide|card|tela|página)\s*\d+)\s*[:.)\-]?[ \t]*\n*",
                   "", texto, flags=re.IGNORECASE)
    paragrafos = []
    for par in re.split(r"\n\s*\n", texto):
        linhas = [l.strip() for l in par.split("\n") if l.strip()]
        if not linhas:
            continue
        junto = linhas[0]
        for linha in linhas[1:]:
            # Junta só quebra no meio de frase: a próxima linha começa com
            # minúscula, ou a anterior termina em vírgula. Mantém itens de
            # lista e títulos ("**Fonte 1**" + "Uma lei mudou?").
            meio_de_frase = (linha[:1].islower() or junto.endswith(",")) and not _ITEM_DE_LISTA.match(linha)
            junto += (" " if meio_de_frase else "\n") + linha
        paragrafos.append(junto)
    return "\n\n".join(paragrafos).strip()


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

    oab = segue_oab(perfil)
    saida = SAIDA_JSON_POST if oab else SAIDA_JSON_POST.replace(
        "pontos que um advogado precisa conferir antes de publicar (afirmações jurídicas, regra da OAB, dado da notícia)",
        "pontos que precisam ser conferidos antes de publicar (afirmações, dados, números, nomes de menus ou funções, dado da notícia)")
    system = "\n\n".join(p for p in [
        ("Você é o redator de redes sociais de um advogado. Escreve em português do Brasil, linguagem "
         "simples, sem juridiquês, pra quem não é da área.") if oab else
        ("Você é o redator de redes sociais de um profissional ou de uma marca. Escreve em português do "
         "Brasil, linguagem simples e direta, pra quem não é especialista no assunto."),
        _bloco_perfil(perfil),
        (perfil.get("publico") or "").strip(),
        _bloco_dna(perfil),
        REGRAS_OAB if oab else REGRAS_GERAIS,
        INSTRUCOES_VOZ.get(perfil.get("voz") or "neutra", INSTRUCOES_VOZ["neutra"]),
        "TOM\n" + ESTILOS_ESCRITA.get(opcoes.get("estilo_escrita"), ESTILOS_ESCRITA["educativo"]),
        REGRAS_FORMATO[formato].format(n_slides=n_slides, cta_regra="CTA permitido pelas regras da OAB" if oab else "CTA claro e direto"),
        saida,
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
        pedido.append(f"CTA DESEJADO (ajuste se ferir a regra da OAB): {opcoes['cta']}" if oab else f"CTA DESEJADO: {opcoes['cta']}")
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
    dados["hashtags"] = _limpar_hashtags(dados.get("hashtags") or [])
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

    oab = segue_oab(perfil)
    system = "\n\n".join(p for p in [
        "Você é o estrategista de conteúdo de um advogado no Instagram." if oab
        else "Você é o estrategista de conteúdo de um profissional ou de uma marca no Instagram.",
        _bloco_perfil(perfil),
        (perfil.get("publico") or "").strip(),
        REGRAS_OAB if oab else REGRAS_GERAIS,
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


SAIDA_JSON_AREA = """SAÍDA — responda SOMENTE com um JSON válido (sem texto antes ou depois, sem ```):
{
  "area": "nome da área de atuação, bem escrito (ex.: Direito Agrário)",
  "frentes": [{"nome": "nome curto do tema (até 3 palavras)", "descricao": "o que entra nesse tema, em uma linha"}],
  "publico": "texto no formato abaixo"
}
Formato do "publico" (use exatamente estes 3 títulos, com itens começando por "- "):
QUEM É O PÚBLICO
- ...
O QUE ELES SENTEM (e quase nunca falam)
- ...
OS "INIMIGOS" DO PÚBLICO
- ..."""


def sugerir_area(area: str, sobre: str = "") -> tuple[dict, dict]:
    """Monta temas ("frentes") e público pra QUALQUER área de atuação.
    Devolve (sugestão, uso)."""
    area = (area or "").strip()[:120]
    if not area:
        raise ValueError("Informe a área de atuação.")
    system = "\n\n".join([
        "Você é estrategista de conteúdo pra advogados no Instagram. Conhece o dia a dia das várias áreas do "
        "Direito no Brasil e o que o cliente leigo sente em cada uma.",
        "TAREFA: pra área informada, defina de 3 a 5 temas (frentes) que rendem conteúdo educativo e útil pro "
        "cliente final, e descreva o público: quem é, o que sente e quem ele culpa quando algo dá errado. "
        "Linguagem simples, sem juridiquês, sem promessas de resultado.",
        SAIDA_JSON_AREA,
    ])
    pedido = f"ÁREA DE ATUAÇÃO: {area}"
    if (sobre or "").strip():
        pedido += f"\nCONTEXTO DO ADVOGADO: {sobre.strip()[:800]}"
    resposta = _cliente().messages.create(model=MODELO, max_tokens=2000, system=system,
                                          messages=[{"role": "user", "content": pedido}])
    dados = _extrair_json(_ultimo_texto(resposta))
    frentes = []
    for f in dados.get("frentes") or []:
        nome = _sem_travessao(str((f or {}).get("nome", "")))[:60]
        if nome:
            frentes.append({"nome": nome, "descricao": _sem_travessao(str(f.get("descricao", "")))[:300]})
    publico = _sem_travessao(str(dados.get("publico") or ""))[:6000]
    if not frentes or not publico:
        raise RuntimeError("A IA não conseguiu montar os temas dessa área. Tente escrever a área de outro jeito.")
    return {"area": _sem_travessao(str(dados.get("area") or area))[:200], "frentes": frentes[:6], "publico": publico}, extrair_uso(resposta)


def sugerir_temas(perfil: dict, quantidade: int = 8) -> tuple[list, dict]:
    """Ideias curtas de tema pra tela de criar post (sem busca na web).
    Devolve ([{"tema", "frente"}], uso)."""
    frentes = [f.get("nome") for f in perfil.get("frentes") or [] if f.get("nome")]
    oab = segue_oab(perfil)
    system = "\n\n".join(p for p in [
        "Você sugere temas de posts pro Instagram, específicos e com cara de dúvida real do público.",
        _bloco_perfil(perfil),
        (perfil.get("publico") or "").strip(),
        REGRAS_OAB if oab else REGRAS_GERAIS,
        f"""SAÍDA — SOMENTE um JSON válido (sem texto antes ou depois), assim:
{{"sugestoes": [{{"tema": "tema curto, até 9 palavras, sem ponto final", "frente": "um destes: {", ".join(frentes) or "Geral"}"}}]}}
Gere {quantidade} sugestões variadas (erro comum, mito x verdade, passo a passo, o que fazer quando...),
distribuídas entre os temas da área. Nada de travessão.""",
    ] if p)
    resposta = _cliente().messages.create(model=MODELO, max_tokens=900, system=system,
                                          messages=[{"role": "user", "content": "Sugira os temas agora."}])
    dados = _extrair_json(_ultimo_texto(resposta))
    saida = []
    for s in dados.get("sugestoes") or []:
        tema = _sem_travessao(str((s or {}).get("tema") or "")).strip().rstrip(".")[:90]
        if tema:
            frente = str(s.get("frente") or "")
            saida.append({"tema": tema, "frente": frente if frente in frentes else (frentes[0] if frentes else "")})
    return saida[:quantidade], extrair_uso(resposta)


def sugestoes_basicas(perfil: dict) -> list:
    """Sem IA: transforma as descrições dos temas da área em sugestões."""
    saida = []
    for f in perfil.get("frentes") or []:
        for pedaco in re.split(r"[,;]", f.get("descricao") or ""):
            pedaco = pedaco.strip().rstrip(".")
            if 3 <= len(pedaco) <= 80:
                saida.append({"tema": pedaco[0].upper() + pedaco[1:], "frente": f.get("nome") or ""})
    return saida[:8]


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
