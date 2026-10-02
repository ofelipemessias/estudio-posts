"""
render_post.py — desenha as artes do Estúdio de Posts (PNG 1080x1350,
formato 4:5 do Instagram) no visual de tweet: avatar + nome + selo +
@ + texto. Mesmo estilo dos carrosséis que o escritório já usa.

Baseado no render_slide.py da skill "carrosseis-tweet" (licença MIT),
adaptado pra rodar dentro do servidor:
- não depende de fonte baixada da internet: procura Roboto (instalada
  pelo pacote fonts-roboto do Dockerfile), depois Liberation e DejaVu;
- aceita destaque de palavras com **asterisco duplo** no texto que a
  IA devolve (ex.: "O banco **não pode** se negar");
- três estilos prontos (claro, escuro, marca) + cores personalizadas
  vindas da configuração do módulo.
"""
import glob
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont

CANVAS_W, CANVAS_H = 1080, 1350
MARGIN_X = 80
AVATAR_SIZE = 100
NAME_SIZE = 36
HANDLE_SIZE = 28
TEXT_SIZE_PADRAO = 56
TEXT_SIZE_MIN = 34

ESTILOS = {
    "escuro": {"fundo": "#000000", "texto": "#E7E9EA", "handle": "#71767B", "selo": "#1D9BF0", "destaque": "#01CF11"},
    "claro": {"fundo": "#FFFFFF", "texto": "#0F1419", "handle": "#536471", "selo": "#1D9BF0", "destaque": "#1D9BF0"},
    "marca": {"fundo": "#022249", "texto": "#FFFFFF", "handle": "#9FB3CC", "selo": "#01CF11", "destaque": "#01CF11"},
}

_CACHE_FONTES = {}


PASTA_FONTES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _achar_fonte(peso: str) -> str:
    """Usa primeiro as fontes que vêm dentro do projeto (pasta fonts/,
    Liberation Sans, licença SIL OFL) -- assim o visual é igual no
    Windows, no Docker ou em qualquer servidor."""
    embutida = os.path.join(PASTA_FONTES, "LiberationSans-Bold.ttf" if peso == "bold" else "LiberationSans-Regular.ttf")
    if os.path.exists(embutida):
        return embutida
    nomes = {
        "regular": ["Roboto-Regular.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"],
        "bold": ["Roboto-Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    }[peso]
    for pasta in ("/usr/share/fonts", "C:/Windows/Fonts"):
        for nome in nomes:
            achados = glob.glob(f"{pasta}/**/{nome}", recursive=True)
            if achados:
                return sorted(achados)[0]
    raise FileNotFoundError("Nenhuma fonte encontrada (a pasta fonts/ do projeto deveria ter a Liberation Sans).")


def carregar_fonte(peso: str, tamanho: int):
    chave = (peso, tamanho)
    if chave not in _CACHE_FONTES:
        _CACHE_FONTES[chave] = ImageFont.truetype(_achar_fonte(peso), tamanho)
    return _CACHE_FONTES[chave]


def montar_paleta(estilo: str, cores_personalizadas: dict | None = None) -> dict:
    paleta = dict(ESTILOS.get(estilo) or ESTILOS["escuro"])
    for chave, valor in (cores_personalizadas or {}).items():
        if valor and isinstance(valor, str) and valor.startswith("#") and len(valor) in (4, 7):
            paleta[chave] = valor
    return paleta


# ---------------------------------------------------------------------------
# Avatar e selo (desenhados 4x maiores e reduzidos, pra borda sair suave)
# ---------------------------------------------------------------------------

def _avatar_circular(caminho: str, tamanho: int, ss: int = 4):
    grande = tamanho * ss
    im = Image.open(caminho).convert("RGBA")
    w, h = im.size
    lado = min(w, h)
    im = im.crop(((w - lado) // 2, (h - lado) // 2, (w + lado) // 2, (h + lado) // 2)).resize((grande, grande), Image.LANCZOS)
    mascara = Image.new("L", (grande, grande), 0)
    ImageDraw.Draw(mascara).ellipse((ss, ss, grande - 1 - ss, grande - 1 - ss), fill=255)
    im.putalpha(mascara)
    return im.resize((tamanho, tamanho), Image.LANCZOS)


def _avatar_inicial(tamanho: int, nome: str, cor_fundo: str, cor_texto: str, ss: int = 4):
    grande = tamanho * ss
    im = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, grande - 1, grande - 1), fill=cor_fundo)
    inicial = ((nome or "?").strip() or "?")[0].upper()
    fonte = carregar_fonte("bold", int(grande * 0.45))
    bbox = d.textbbox((0, 0), inicial, font=fonte)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((grande - tw) / 2 - bbox[0], (grande - th) / 2 - bbox[1]), inicial, font=fonte, fill=cor_texto)
    return im.resize((tamanho, tamanho), Image.LANCZOS)


def _selo_verificado(img, x, y, cor, tamanho: int = 32, ss: int = 4):
    grande = tamanho * ss
    selo = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(selo)
    d.ellipse((ss, ss, grande - 1 - ss, grande - 1 - ss), fill=cor)
    lw = 3 * ss
    pontos = [(8 * ss, 16 * ss), (14 * ss, 22 * ss), (24 * ss, 10 * ss)]
    d.line(pontos[:2], fill="white", width=lw)
    d.line(pontos[1:], fill="white", width=lw)
    r = lw // 2
    for cx, cy in pontos:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="white")
    selo = selo.resize((tamanho, tamanho), Image.LANCZOS)
    img.paste(selo, (int(x), int(y)), selo)


# ---------------------------------------------------------------------------
# Texto com destaque (**palavra**)
# ---------------------------------------------------------------------------

def _tokenizar(linha: str):
    """Transforma 'Caiu no **Pix**?' numa lista de PALAVRAS, onde cada
    palavra é uma lista de pedaços (texto, destacado?) -- assim o '?'
    colado no '**Pix**' continua grudado nele, sem espaço no meio."""
    palavras, atual, destacado = [], [], False
    for i, pedaco in enumerate(linha.split("**")):
        if i > 0:
            destacado = not destacado
        if not pedaco:
            continue
        if pedaco[0].isspace() and atual:
            palavras.append(atual)
            atual = []
        partes = pedaco.split()
        for j, parte in enumerate(partes):
            if j > 0 and atual:
                palavras.append(atual)
                atual = []
            atual.append((parte, destacado))
        if pedaco[-1].isspace() and atual:
            palavras.append(atual)
            atual = []
    if atual:
        palavras.append(atual)
    return palavras


def _largura_palavra(palavra, fonte, fonte_bold):
    return sum((fonte_bold if d else fonte).getlength(t) for t, d in palavra)


def _quebrar(texto: str, fonte, fonte_bold, largura_max: int):
    """Devolve uma lista de linhas; cada linha é uma lista de palavras
    (ver _tokenizar). Linha vazia ([]) = espaço entre parágrafos."""
    linhas = []
    espaco = fonte.getlength(" ")
    paragrafos = texto.replace("\r", "").split("\n\n")
    for i, par in enumerate(paragrafos):
        for trecho in par.split("\n"):
            atual, largura_atual = [], 0.0
            for palavra in _tokenizar(trecho):
                w = _largura_palavra(palavra, fonte, fonte_bold)
                if atual and largura_atual + w > largura_max:
                    linhas.append(atual)
                    atual, largura_atual = [], 0.0
                atual.append(palavra)
                largura_atual += w + espaco
            if atual:
                linhas.append(atual)
        if i < len(paragrafos) - 1:
            linhas.append([])
    return linhas


def _layout_texto(texto: str, altura_disponivel: int, largura: int = CANVAS_W - 2 * MARGIN_X,
                  tam_max: int = TEXT_SIZE_PADRAO, tam_min: int = TEXT_SIZE_MIN, peso: str = "regular", entrelinha: float = 1.36):
    """Escolhe o maior tamanho de fonte (entre tam_max e tam_min) em que o
    texto cabe na área disponível."""
    tamanho = tam_max
    while True:
        fonte = carregar_fonte(peso, tamanho)
        fonte_bold = carregar_fonte("bold", tamanho)
        altura_linha = int(tamanho * entrelinha)
        linhas = _quebrar(texto, fonte, fonte_bold, largura)
        altura = sum(altura_linha if l else altura_linha // 2 for l in linhas)
        if altura <= altura_disponivel or tamanho <= tam_min:
            return fonte, fonte_bold, altura_linha, linhas, altura
        tamanho -= 2


def _largura_linha(linha, fonte, fonte_bold):
    return sum(_largura_palavra(p, fonte, fonte_bold) for p in linha) + fonte.getlength(" ") * max(0, len(linha) - 1)


def _escrever(draw, linhas, fonte, fonte_bold, altura_linha, x0, y, paleta, largura=None, centralizar=False,
              cor_texto=None, negrito_tudo=False):
    """Escreve as linhas (com **destaque**). Devolve o y final."""
    cor_base = cor_texto or paleta["texto"]
    for linha in linhas:
        if not linha:
            y += altura_linha // 2
            continue
        x = x0
        if centralizar and largura:
            x = x0 + (largura - _largura_linha(linha, fonte, fonte_bold)) / 2
        for palavra in linha:
            for pedaco, destacada in palavra:
                f = fonte_bold if (destacada or negrito_tudo) else fonte
                draw.text((x, y), pedaco, font=f, fill=paleta["destaque"] if destacada else cor_base)
                x += f.getlength(pedaco)
            x += fonte.getlength(" ")
        y += altura_linha
    return y


# ---------------------------------------------------------------------------
# Formatos de tela e modelos de arte
# ---------------------------------------------------------------------------

# (largura, altura, margem de cima, margem de baixo). No Story, as margens
# protegem o texto da barra de progresso e do campo de resposta do Instagram.
TELAS = {
    "feed": (1080, 1350, 90, 90),
    "story": (1080, 1920, 260, 340),
}

MODELOS_ARTE = {
    "tweet": "Tweet (estilo post do X)",
    "editorial": "Editorial (título grande)",
    "minimal": "Minimalista (frase centralizada)",
}


def _identidade(identidade):
    nome = identidade.get("nome") or "Seu nome"
    handle = identidade.get("handle") or ""
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    return nome, handle


def _avatar(identidade, paleta, tamanho):
    avatar_path = identidade.get("avatar_path")
    if avatar_path and os.path.exists(avatar_path):
        return _avatar_circular(avatar_path, tamanho)
    return _avatar_inicial(tamanho, identidade.get("nome", ""), paleta["destaque"], paleta["fundo"])


def _slide_tweet(img, draw, texto, identidade, paleta, W, H, topo, base):
    fonte_nome = carregar_fonte("bold", NAME_SIZE)
    fonte_handle = carregar_fonte("regular", HANDLE_SIZE)
    gap = 32
    altura_max_texto = H - topo - base - AVATAR_SIZE - gap
    fonte, fonte_bold, altura_linha, linhas, altura_texto = _layout_texto(texto, altura_max_texto, W - 2 * MARGIN_X)
    altura_total = AVATAR_SIZE + gap + altura_texto
    y0 = max(topo - 30, topo + (H - topo - base - altura_total) // 2)
    avatar = _avatar(identidade, paleta, AVATAR_SIZE)
    img.paste(avatar, (MARGIN_X, y0), avatar)
    nome, handle = _identidade(identidade)
    x_nome = MARGIN_X + AVATAR_SIZE + 20
    draw.text((x_nome, y0 + 10), nome, font=fonte_nome, fill=paleta["texto"])
    _selo_verificado(img, x_nome + draw.textlength(nome, font=fonte_nome) + 10, y0 + 18, paleta["selo"])
    draw.text((x_nome, y0 + 52), handle, font=fonte_handle, fill=paleta["handle"])
    _escrever(draw, linhas, fonte, fonte_bold, altura_linha, MARGIN_X, y0 + AVATAR_SIZE + gap, paleta)


def _slide_editorial(img, draw, texto, identidade, paleta, W, H, topo, base, indice, total):
    """Título grande (1º parágrafo), faixa de destaque e texto de apoio."""
    mx = 90
    largura = W - 2 * mx
    partes = [p for p in texto.replace("\r", "").split("\n\n") if p.strip()]
    titulo, corpo = (partes[0], "\n\n".join(partes[1:])) if partes else ("", "")
    nome, handle = _identidade(identidade)
    # topo: marca
    fonte_marca = carregar_fonte("bold", 30)
    draw.text((mx, topo - 20), (nome + (f"  ·  {handle}" if handle else "")).upper(), font=fonte_marca, fill=paleta["handle"])
    # rodapé: contador e "arraste"
    fonte_rod = carregar_fonte("bold", 30)
    y_rod = H - base + 20
    if total > 1:
        draw.text((mx, y_rod), f"{indice}/{total}", font=fonte_rod, fill=paleta["handle"])
        if indice < total and H <= 1400:  # no Story passa com toque, não com "arraste"
            seta = "Arraste  →"
            draw.text((W - mx - draw.textlength(seta, font=fonte_rod), y_rod), seta, font=fonte_rod, fill=paleta["destaque"])
    # área útil
    area_topo, area_fim = topo + 60, H - base - 30
    disponivel = area_fim - area_topo
    if corpo:
        ft, ftb, alt_t, lin_t, h_t = _layout_texto(titulo, int(disponivel * 0.5), largura, 92, 54, peso="bold", entrelinha=1.18)
        fc, fcb, alt_c, lin_c, h_c = _layout_texto(corpo, disponivel - h_t - 70, largura, 54, 30)
    else:
        ft, ftb, alt_t, lin_t, h_t = _layout_texto(titulo, disponivel - 40, largura, 104, 54, peso="bold", entrelinha=1.18)
        lin_c, h_c = [], 0
    bloco = 16 + 34 + h_t + (70 + h_c if lin_c else 0)
    y = area_topo + max(0, (disponivel - bloco) // 2)
    draw.rectangle([mx, y, mx + 110, y + 14], fill=paleta["destaque"])
    y += 14 + 34
    y = _escrever(draw, lin_t, ft, ftb, alt_t, mx, y, paleta, negrito_tudo=True)
    if lin_c:
        y += 70 - alt_t // 4
        _escrever(draw, lin_c, fc, fcb, alt_c, mx, y, paleta)


def _slide_minimal(img, draw, texto, identidade, paleta, W, H, topo, base):
    """Frase grande e centralizada, com moldura fina na cor de destaque."""
    borda = 46
    draw.rectangle([borda, borda, W - borda, H - borda], outline=paleta["destaque"], width=6)
    mx = 130
    largura = W - 2 * mx
    nome, handle = _identidade(identidade)
    fonte_rod = carregar_fonte("bold", 30)
    assinatura = handle or nome
    y_ass = H - max(base, borda + 80) - 10
    draw.text(((W - draw.textlength(assinatura, font=fonte_rod)) / 2, y_ass), assinatura, font=fonte_rod, fill=paleta["handle"])
    disponivel = y_ass - topo - 60
    f, fb, alt, linhas, h = _layout_texto(texto, disponivel, largura, 100 if H > 1400 else 92, 40, entrelinha=1.28)
    y = topo + max(0, (disponivel - h) // 2)
    _escrever(draw, linhas, f, fb, alt, mx, y, paleta, largura=largura, centralizar=True)


def desenhar_slide(texto: str, identidade: dict, paleta: dict, caminho_saida: str,
                   modelo: str = "tweet", tela: str = "feed", indice: int = 1, total: int = 1):
    """identidade: {"nome", "handle", "avatar_path" (opcional)}.
    modelo: tweet | editorial | minimal. tela: feed (1080x1350) | story (1080x1920)."""
    W, H, topo, base = TELAS.get(tela, TELAS["feed"])
    img = Image.new("RGB", (W, H), paleta["fundo"])
    draw = ImageDraw.Draw(img)
    if modelo == "editorial":
        _slide_editorial(img, draw, texto, identidade, paleta, W, H, topo, base, indice, total)
    elif modelo == "minimal":
        _slide_minimal(img, draw, texto, identidade, paleta, W, H, topo, base)
    else:
        _slide_tweet(img, draw, texto, identidade, paleta, W, H, topo, base)
    img.save(caminho_saida, "PNG", optimize=True)
    return caminho_saida


def desenhar_todos(textos: list, identidade: dict, paleta: dict, pasta: str, modelo: str = "tweet", tela: str = "feed") -> list:
    os.makedirs(pasta, exist_ok=True)
    for antigo in glob.glob(os.path.join(pasta, "slide_*.png")):
        os.remove(antigo)
    nomes = []
    for i, texto in enumerate(textos, 1):
        nome = f"slide_{i:02d}.png"
        desenhar_slide(texto, identidade, paleta, os.path.join(pasta, nome), modelo, tela, i, len(textos))
        nomes.append(nome)
    return nomes


def empacotar_zip(pasta: str, nomes_slides: list, extras: dict | None = None, nome_zip: str = "post.zip") -> str:
    """extras: {"legenda.txt": "conteúdo", ...} — textos que vão junto no zip."""
    caminho = os.path.join(pasta, nome_zip)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome in nomes_slides:
            zf.write(os.path.join(pasta, nome), arcname=nome)
        for nome, conteudo in (extras or {}).items():
            zf.writestr(nome, conteudo)
    return caminho
