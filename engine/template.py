"""
PDF Engine Evolux — template.py
Fiel ao ModeloDeCapa.svg / aula para gpt.pdf

Estrutura da capa (extraída do SVG):
  1. Fundo NAVY #011641 (página inteira)
  2. Foto full-bleed (se existir), sobre o navy
  3. Triângulo navy sobre a foto (recorte superior-esquerdo)
  4. Paralelogramo dourado diagonal  ← coordenadas exatas do SVG
  5. Segundo acento dourado (triângulo esquerdo)
  6. Caixa branca + logo — canto superior-direito (posição exata do SVG)
  7. "Aula XX" em amarelo (#f9d549)
  8. Título em branco, grande

Uso:
  python engine/template.py aula03
  python engine/template.py aula03 --md /caminho/arquivo.md
"""

import os, sys, json

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    PageBreak, KeepTogether
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Dimensões A4 ──
W, H = A4   # 595.28 × 841.89 pt

# ── Cores (idênticas ao SVG) ──
NAVY   = colors.HexColor("#011641")
GOLD   = colors.HexColor("#e2a331")
YELLOW = colors.HexColor("#f9d549")
GRAY   = colors.HexColor("#4A5568")

# ── Fontes ──
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")

def _register_fonts():
    r = os.path.join(_FONT_DIR, "Montserrat-Regular.ttf")
    b = os.path.join(_FONT_DIR, "Montserrat-Bold.ttf")
    if os.path.exists(r) and os.path.exists(b):
        pdfmetrics.registerFont(TTFont("Montserrat", r))
        pdfmetrics.registerFont(TTFont("Montserrat-Bold", b))
        return "Montserrat", "Montserrat-Bold"
    return "Helvetica", "Helvetica-Bold"

FONT_REG, FONT_BOLD = _register_fonts()

# ── Logo global (fallback) ──
_LOGO_GLOBAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "instruçoes", "logo.jpeg")

def _logo_path(assets):
    for n in ("logo.png", "logo.jpg", "logo.jpeg"):
        p = os.path.join(assets, n)
        if os.path.exists(p): return p
    if os.path.exists(_LOGO_GLOBAL): return _LOGO_GLOBAL
    return None

def _cover_path(assets):
    for n in ("cover.jpg", "cover.jpeg", "cover.png"):
        p = os.path.join(assets, n)
        if os.path.exists(p): return p
    return None

# ── Estilos ──
H1 = ParagraphStyle("H1", fontName=FONT_BOLD, fontSize=20,
                    textColor=NAVY, spaceBefore=20, spaceAfter=8, leading=26)
H2 = ParagraphStyle("H2", fontName=FONT_BOLD, fontSize=15,
                    textColor=NAVY, spaceBefore=14, spaceAfter=6, leading=20)
H3 = ParagraphStyle("H3", fontName=FONT_BOLD, fontSize=12,
                    textColor=GRAY, spaceBefore=8, spaceAfter=4, leading=16)
BODY = ParagraphStyle("BODY", fontName=FONT_REG, fontSize=11,
                      leading=17, textColor=NAVY, spaceAfter=6)
LIST = ParagraphStyle("LIST", fontName=FONT_REG, fontSize=11,
                      leading=16, textColor=NAVY, leftIndent=16, spaceAfter=3)
BOX  = ParagraphStyle("BOX", fontName=FONT_REG, fontSize=11,
                      backColor=colors.HexColor("#F5F6FA"),
                      borderColor=GOLD, borderWidth=4,
                      borderPadding=10, leading=16,
                      textColor=NAVY, spaceAfter=10, spaceBefore=8)


# ════════════════════════════════════════
# CAPA — fiel ao SVG de referência
# ════════════════════════════════════════
def draw_cover(canvas, doc, meta: dict, assets: str):
    canvas.saveState()

    # ── 1. FUNDO NAVY (base de toda a página) ──
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # ── 2. FOTO full-bleed (se houver assets/cover.jpg) ──
    cover = _cover_path(assets)
    if cover:
        canvas.drawImage(cover, 0, 0, width=W, height=H,
                         preserveAspectRatio=False, mask="auto")

    # ── 3. TRIÂNGULO NAVY sobre a foto — recorte superior-esquerdo ──
    # Cria área escura no canto superior-esquerdo (só aparece sobre a foto)
    # ~42% da largura no topo, desce até ~46% da altura à esquerda
    canvas.setFillColor(NAVY)
    p = canvas.beginPath()
    p.moveTo(0,         H)           # canto sup-esq
    p.lineTo(W * 0.42,  H)           # 42% ao longo do topo
    p.lineTo(0,         H * 0.46)    # esquerda, 54% de cima → 46% de baixo
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # ── 4. PARALELOGRAMO DOURADO PRINCIPAL ──
    # Coordenadas SVG: M 380.23 0.65 L 620.97 141.05 L 240.90 792.75 L 0.16 652.35
    # Convertendo para RL (RL_y = H - SVG_y, usando H=841.89):
    #   (380.23, 841.24)  (620.97, 700.84)  (240.90, 49.14)  (0.16, 189.54)
    canvas.setFillColor(GOLD)
    p = canvas.beginPath()
    p.moveTo(380.23, H - 0.65)     # topo, 64% da largura
    p.lineTo(620.97, H - 141.05)   # fora da página à direita
    p.lineTo(240.90, H - 792.75)   # base, 40% da largura
    p.lineTo(  0.16, H - 652.35)   # esquerda, 23% de baixo
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # ── 5. ACENTO DOURADO — triângulo esquerdo (segundo path do SVG) ──
    # SVG: M -57.46 0.09 L 183.28 140.50 L -196.79 792.19 L -437.53 651.79
    # Porção visível interseccionada com x≥0 (calculada geometricamente):
    #   (0, H-33.5)=(0, 808.4)  →  (183.28, H-140.50)=(183.28, 701.4)  →  (0, H-454.6)=(0, 387.3)
    p = canvas.beginPath()
    p.moveTo(  0,      H - 33.5)   # (0, ~808) — topo visível na borda esq
    p.lineTo(183.28,   H - 140.5)  # (183, ~701) — ponto máximo à direita
    p.lineTo(  0,      H - 454.6)  # (0, ~387) — base visível na borda esq
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # ── 6. CAIXA BRANCA DO LOGO — posição exata do SVG ──
    # SVG rect: (436, 10) → (584, 134)  →  w=148, h=124
    # RL: x=436, y = H-134 = ~708, w=148, h=124
    LBOX_X, LBOX_Y = 436, H - 134
    LBOX_W, LBOX_H = 148, 124
    canvas.setFillColor(colors.white)
    canvas.rect(LBOX_X, LBOX_Y, LBOX_W, LBOX_H, fill=1, stroke=0)

    logo = _logo_path(assets)
    if logo:
        pad = 10
        canvas.drawImage(
            logo,
            LBOX_X + pad,  LBOX_Y + pad,
            width=LBOX_W - 2*pad, height=LBOX_H - 2*pad,
            preserveAspectRatio=True, mask="auto"
        )

    # ── 7. TEXTO "Aula XX" — amarelo (#f9d549) ──
    # Posicionado logo ACIMA do paralelogramo dourado
    # Gold upper-edge em x=57pt (2cm): RL_y = 190 + 57*(841-190)/380 ≈ 288
    # → colocamos "Aula" em y≈308 (acima do gold, sobre navy/foto)
    canvas.setFillColor(YELLOW)
    canvas.setFont(FONT_BOLD, 14)
    canvas.drawString(2 * cm, H - 534, f"Aula {meta.get('aula', '01')}")

    # ── 8. TÍTULO — branco, grande, dentro do paralelogramo dourado ──
    title = meta.get("title", "Sem título")
    words = title.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= 13:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)

    font_sz = 60
    leading = 74
    if len(lines) > 3:
        font_sz = 44
        leading = 54

    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, font_sz)
    # Primeira linha logo abaixo do "Aula XX"
    title_y = H - 534 - 18 - font_sz   # gap de 18pt abaixo do label
    for i, line in enumerate(lines):
        canvas.drawString(2 * cm, title_y - i * leading, line)

    canvas.restoreState()


# ════════════════════════════════════════
# PÁGINAS INTERNAS — modeloDePagina.svg
# ════════════════════════════════════════
def header_footer(canvas, doc, assets: str):
    """
    Layout extraído de modeloDePagina.svg.
    """
    canvas.saveState()
    
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        
        svg_path = os.path.join(os.path.dirname(__file__), "..", "instruçoes", "modeloDePagina.svg")
        if os.path.exists(svg_path):
            drawing = svg2rlg(svg_path)
            if drawing:
                # Escala o SVG para preencher a folha A4 (W, H)
                sx = W / drawing.width
                sy = H / drawing.height
                drawing.scale(sx, sy)
                renderPDF.draw(drawing, canvas, 0, 0)
    except Exception as e:
        print("Erro ao carregar o SVG:", e)
        pass

    # A página 1 real será a página 2 visual
    canvas.setFont(FONT_REG, 10)
    canvas.setFillColor(NAVY)
    canvas.drawRightString(W - 2 * cm, 1.8 * cm, f"Página {doc.page + 1}")

    canvas.restoreState()


# ════════════════════════════════════════
# PARSER MARKDOWN
# ════════════════════════════════════════
def parse_md(md_path: str, assets: str) -> list:
    story, in_box, buf = [], False, []

    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    for raw in lines:
        line = raw.rstrip("\n").rstrip()

        if not line.strip():
            if not in_box: story.append(Spacer(1, 6))
            continue

        line = line.strip()

        if line == "---":           story.append(Spacer(1, 10)); continue
        if line == "[BOX]":         in_box = True; buf = []; continue
        if line == "[/BOX]":
            story.append(Paragraph(" ".join(buf), BOX)); in_box = False; continue
        if in_box:                  buf.append(line); continue

        if line.startswith("### "): story.append(Paragraph(line[4:], H3)); continue
        if line.startswith("## "):  story.append(Paragraph(line[3:], H2)); continue
        if line.startswith("# "):   story.append(Paragraph(line[2:], H1)); continue
        if line.startswith("- "):   story.append(Paragraph("• " + line[2:], LIST)); continue

        if line.startswith("[IMG:") and line.endswith("]"):
            name = line[5:-1].strip()
            img_p = os.path.join(assets, name)
            if os.path.exists(img_p):
                try:
                    img = Image(img_p)
                    img._restrictSize(W - 4*cm, H - 10*cm)
                    img.hAlign = "CENTER"
                    story.append(KeepTogether([img, Spacer(1, 10)]))
                except Exception as e:
                    story.append(Paragraph(f"⚠️ <i>[Erro ao carregar a imagem {name}. Converta para .jpg ou .png]</i>", BODY))
                    story.append(Spacer(1, 10))
            continue

        story.append(Paragraph(line, BODY))

    return story


# ════════════════════════════════════════
# BUILD — modo projeto (legado)
# ════════════════════════════════════════
def build(project: str, base_dir: str = "projects", md_file: str = None):
    """Build a partir de uma pasta de projeto (projects/aula03/)."""
    base      = os.path.join(base_dir, project)
    meta_path = os.path.join(base, "meta.json")
    assets    = os.path.join(base, "assets")
    output    = os.path.join(base, "output.pdf")

    if md_file:
        md_path = os.path.abspath(md_file)
        if not os.path.exists(md_path):
            raise FileNotFoundError(f".md não encontrado: {md_path}")
    else:
        md_path = os.path.join(base, "content.md")
        if not os.path.exists(md_path):
            raise FileNotFoundError(f"content.md não encontrado em: {md_path}")

    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"meta.json não encontrado em: {meta_path}")

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    os.makedirs(assets, exist_ok=True)
    return _render(md_path, meta, output, assets)


# ════════════════════════════════════════
# BUILD FROM MD — modo escalável (novo)
# ════════════════════════════════════════
def build_from_md(md_path: str, output_path: str,
                  assets_dir: str = None, meta: dict = None) -> str:
    """
    Gera PDF diretamente de um arquivo .md, sem estrutura de projeto.

    Args:
        md_path:     caminho absoluto do arquivo .md
        output_path: onde salvar o .pdf gerado
        assets_dir:  pasta com cover.jpg / logo (opcional)
        meta:        dicionário com 'title' e 'aula' (auto-extraído se None)
    """
    md_path = os.path.abspath(md_path)
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Arquivo .md não encontrado: {md_path}")

    # ── Auto-detecta meta se não fornecido ──
    if meta is None:
        meta = extract_meta(md_path)

    # ── Pasta de assets: mesmo dir do .md, ou explícita ──
    if assets_dir is None:
        assets_dir = os.path.dirname(md_path)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    return _render(md_path, meta, output_path, assets_dir)


def extract_meta(md_path: str) -> dict:
    """
    Extrai título e número de aula do arquivo .md.

    Estratégias (em ordem de prioridade):
      1. Front-matter YAML entre --- no início do arquivo:
            ---
            title: Necropsia Veterinária
            aula: 03
            ---
      2. Primeiro heading # do arquivo como título
      3. Nome do arquivo (sem extensão) como título
      Número de aula: número presente no nome do arquivo (aula03.md → "03")
    """
    filename = os.path.splitext(os.path.basename(md_path))[0]
    title    = filename
    aula     = "01"

    # Número de aula do nome do arquivo (ex: aula03, modulo02, 05_tema)
    import re
    num_match = re.search(r'(\d+)', filename)
    if num_match:
        aula = num_match.group(1).zfill(2)

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # 1. Front-matter YAML
    fm = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if fm:
        for line in fm.group(1).splitlines():
            if ':' in line:
                key, _, val = line.partition(':')
                key, val = key.strip().lower(), val.strip()
                if key == 'title': title = val
                if key == 'aula':  aula  = str(val).zfill(2)
        return {"title": title, "aula": aula}

    # 2. Primeiro # Heading
    h1 = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()

    return {"title": title, "aula": aula}


def _render(md_path: str, meta: dict, output_path: str, assets_dir: str) -> str:
    """Motor de renderização (Capa removida a pedido)."""
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=3.2*cm, bottomMargin=2.5*cm
    )

    story = parse_md(md_path, assets_dir)

    doc.build(
        story,
        onFirstPage=lambda c, d: header_footer(c, d, assets_dir),
        onLaterPages=lambda c, d: header_footer(c, d, assets_dir),
    )
    print(f"  ✅ {os.path.basename(output_path)}")
    return output_path


# ════════════════════════════════════════
# CLI
# ════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python engine/template.py <projeto> [--md arquivo.md]")
        sys.exit(1)
    _proj = sys.argv[1]
    _md   = None
    if "--md" in sys.argv:
        idx = sys.argv.index("--md")
        if idx + 1 < len(sys.argv): _md = sys.argv[idx + 1]
    build(_proj, md_file=_md)
