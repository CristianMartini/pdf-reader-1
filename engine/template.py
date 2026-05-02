"""
PDF Engine Evolux — template.py
Auditado e reescrito para corrigir:
  - Front-matter (---/title/aula) vazando como texto no PDF
  - Logo com fundo preto/branco (JPEG sem canal alpha)
  - Sobreposição de texto e imagens
  - Separadores --- do conteúdo renderizando errado
  - Build unificado (capa + conteúdo em um único doc.build)
  - Margens e tipografia ABNT

Estrutura da capa (fiel ao ModeloDeCapa.svg):
  1. Fundo NAVY #011641
  2. Foto full-bleed (cover.jpg se existir)
  3. Triângulo NAVY — recorte sup-esq
  4. Paralelogramo dourado diagonal
  5. Acento dourado — triângulo esquerdo
  6. Logo — sem fundo (mask auto para PNG/WebP, sem box branco)
  7. "Aula XX" em amarelo
  8. Título em branco
"""

import os
import sys
import json
import re
import tempfile
from functools import lru_cache

try:
    from PIL import Image as PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    PageBreak, KeepTogether, HRFlowable, Table, TableStyle
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Dimensões A4 ──
W, H = A4  # 595.28 × 841.89 pt

# ── Cores ──
NAVY   = colors.HexColor("#011641")
GOLD   = colors.HexColor("#e2a331")
YELLOW = colors.HexColor("#f9d549")
GRAY   = colors.HexColor("#4A5568")
LGRAY  = colors.HexColor("#C7D2E8")
BOXBG  = colors.HexColor("#F0F4FA")

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

# ── Caminhos de assets ──
_LOGO_GLOBAL = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instruçoes", "logo.jpeg")
)


def _logo_path(assets: str):
    """Retorna o caminho do logo local ou o global de fallback."""
    for n in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp"):
        p = os.path.join(assets, n)
        if os.path.exists(p):
            return p
    if os.path.exists(_LOGO_GLOBAL):
        return _LOGO_GLOBAL
    return None


def _cover_path(assets: str):
    for n in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp"):
        p = os.path.join(assets, n)
        if os.path.exists(p):
            return p
    return None


def _logo_mask(path: str):
    """
    JPEG não tem canal alpha — usar mask=None.
    PNG/WebP/GIF têm alpha — usar mask='auto'.
    """
    if path and path.lower().endswith((".png", ".webp", ".gif")):
        return "auto"
    return None  # JPEG: sem mask para evitar fundo preto

@lru_cache(maxsize=32)
def _preprocess_image(img_path: str,
                      max_px: int = 1400,
                      quality: int = 80) -> str:
    """
    Redimensiona e converte imagens grandes para JPEG antes de passar ao ReportLab.
    - Imagens <= max_px em ambas as dimensões: retorna o caminho original.
    - Imagens maiores: salva JPEG redimensionado em arquivo temporário.
    - Converte WebP/HEIC/PNG grandes automaticamente para JPEG.
    Retorna o caminho do arquivo a usar (original ou temp).
    """
    if not _PIL_OK:
        return img_path
    try:
        with PILImage.open(img_path) as im:
            w, h = im.size
            ext   = os.path.splitext(img_path)[1].lower()
            # Formatos que ReportLab lida mal: WebP, HEIC, TIFF grandes
            needs_convert = ext in (".webp", ".heic", ".heif", ".tiff", ".tif", ".bmp")
            needs_resize  = (w > max_px or h > max_px)

            if not needs_convert and not needs_resize:
                return img_path  # já pequeno e formato ok

            # Converte para RGB (elimina canal alpha para JPEG)
            if im.mode in ("RGBA", "LA", "P"):
                bg = PILImage.new("RGB", im.size, (255, 255, 255))
                if im.mode == "P":
                    im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")

            if needs_resize:
                im.thumbnail((max_px, max_px), PILImage.LANCZOS)

            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".jpg", prefix="evolux_img_"
            )
            im.save(tmp.name, "JPEG", quality=quality, optimize=True)
            return tmp.name
    except Exception:
        return img_path  # fallback sem crash

# ════════════════════════════════════════
# ESTILOS (ABNT-compatíveis)
H1  = ParagraphStyle("H1",  fontName=FONT_BOLD, fontSize=16,
                     textColor=NAVY, spaceBefore=18, spaceAfter=8, leading=22)
MATERIA_STYLE = ParagraphStyle("MATERIA_STYLE", fontName=FONT_BOLD, fontSize=18,
                     textColor=NAVY, alignment=1)
TITLE_AULA = ParagraphStyle("TITLE_AULA", fontName=FONT_BOLD, fontSize=18,
                     textColor=NAVY, alignment=1)
H2  = ParagraphStyle("H2",  fontName=FONT_BOLD, fontSize=14,
                     textColor=NAVY, spaceBefore=14, spaceAfter=6, leading=19)
H3  = ParagraphStyle("H3",  fontName=FONT_BOLD, fontSize=12,
                     textColor=GRAY, spaceBefore=10, spaceAfter=4, leading=16)
BODY = ParagraphStyle("BODY", fontName=FONT_REG, fontSize=12,
                      leading=18, textColor=NAVY, spaceAfter=8, alignment=4)
LIST = ParagraphStyle("LIST", fontName=FONT_REG, fontSize=12,
                      leading=18, textColor=NAVY, leftIndent=20, spaceAfter=4)
BOX  = ParagraphStyle("BOX",  fontName=FONT_REG, fontSize=11,
                      backColor=BOXBG, borderColor=GOLD, borderWidth=4,
                      borderPadding=10, leading=16,
                      textColor=NAVY, spaceAfter=10, spaceBefore=8)
CAPTION = ParagraphStyle("CAPTION", fontName=FONT_REG, fontSize=9,
                          textColor=GRAY, alignment=1, spaceAfter=6)


# ════════════════════════════════════════
# CAPA — fiel ao SVG de referência
# ════════════════════════════════════════
def draw_cover(canvas, doc, meta: dict, assets: str):
    canvas.saveState()

    # 1. Fundo NAVY
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # 2. Foto full-bleed
    cover = _cover_path(assets)
    if cover:
        canvas.drawImage(cover, 0, 0, width=W, height=H,
                         preserveAspectRatio=False, mask=_logo_mask(cover))

    # 3. Triângulo NAVY — recorte sup-esq
    canvas.setFillColor(NAVY)
    p = canvas.beginPath()
    p.moveTo(0, H)
    p.lineTo(W * 0.42, H)
    p.lineTo(0, H * 0.46)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # 4. Paralelogramo dourado principal
    canvas.setFillColor(GOLD)
    p = canvas.beginPath()
    p.moveTo(380.23, H - 0.65)
    p.lineTo(620.97, H - 141.05)
    p.lineTo(240.90, H - 792.75)
    p.lineTo(  0.16, H - 652.35)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # 5. Acento dourado — triângulo esquerdo
    p = canvas.beginPath()
    p.moveTo(  0,     H - 33.5)
    p.lineTo(183.28,  H - 140.5)
    p.lineTo(  0,     H - 454.6)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)

    # 6. Logo — SEM caixa branca; usa mask correto por extensão
    logo = _logo_path(assets)
    if logo:
        LBOX_X, LBOX_Y = 436, H - 134
        LBOX_W, LBOX_H = 148, 124
        pad = 10
        canvas.drawImage(
            logo,
            LBOX_X + pad, LBOX_Y + pad,
            width=LBOX_W - 2 * pad, height=LBOX_H - 2 * pad,
            preserveAspectRatio=True,
            mask=_logo_mask(logo),
        )

    # 7. "Aula XX"
    canvas.setFillColor(YELLOW)
    canvas.setFont(FONT_BOLD, 14)
    canvas.drawString(2 * cm, H - 534, f"Aula {meta.get('aula', '01')}")

    # 8. Título
    title  = meta.get("title", "Sem título")
    words  = title.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= 13:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    font_sz = 60 if len(lines) <= 3 else 44
    leading  = 74 if len(lines) <= 3 else 54

    canvas.setFillColor(colors.white)
    canvas.setFont(FONT_BOLD, font_sz)
    title_y = H - 534 - 18 - font_sz
    for i, ln in enumerate(lines):
        canvas.drawString(2 * cm, title_y - i * leading, ln)

    canvas.restoreState()


# ════════════════════════════════════════
# CABEÇALHO / RODAPÉ PÁGINAS INTERNAS
# ════════════════════════════════════════
def header_footer(canvas, doc, assets: str):
    """Cabeçalho com logo (sem fundo) + linha dourada. Rod. com paginação centralizada."""
    canvas.saveState()

    header_y = H - 1.9 * cm
    footer_y = 1.6 * cm

    # Logo primeiro (fundo opaco do JPEG fica abaixo da linha)
    logo = _logo_path(assets)
    if logo:
        canvas.drawImage(
            logo,
            2 * cm, header_y - 0.65 * cm,
            width=3.2 * cm, height=1.4 * cm,
            preserveAspectRatio=True,
            mask=_logo_mask(logo),
        )

    # Linha dourada DEPOIS do logo — fica sobre o fundo do JPEG
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.5)
    canvas.line(2 * cm, header_y - 0.55 * cm, W - 2 * cm, header_y - 0.55 * cm)

    # "Material Didático" à direita
    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 10)
    canvas.drawRightString(W - 2 * cm, header_y, "Material Didático")

    # Linha do rod. e número de página
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.8)
    canvas.line(2 * cm, footer_y + 0.4 * cm, W - 2 * cm, footer_y + 0.4 * cm)

    canvas.setFillColor(GRAY)
    canvas.setFont(FONT_REG, 10)
    canvas.drawRightString(W - 2 * cm, footer_y - 0.05 * cm, str(doc.page + 1))

    canvas.restoreState()


# ════════════════════════════════════════
# PARSER MARKDOWN — robusto e auditado
# ════════════════════════════════════════
def parse_md(md_path: str, assets: str, meta: dict = None) -> list:
    """
    Converte .md em lista de flowables ReportLab.

    Busca de imagens (em ordem):
      1. <assets>/<nome>           ← pasta de assets configurada
      2. <dir do .md>/<nome>       ← fallback: mesmo diretório do arquivo .md
    Se não encontrada em nenhum lugar, a linha [IMG:...] é silenciosamente ignorada.
    """
    if meta is None: meta = {}
    materia = meta.get("materia", "Disciplina")
    aula = meta.get("aula", "01")
    
    story: list = [
        Paragraph(materia, MATERIA_STYLE),
        Spacer(1, 10),
        Paragraph(f"Aula {aula}", TITLE_AULA),
        Spacer(1, 24)
    ]
    in_box = False
    buf: list = []

    with open(md_path, encoding="utf-8") as f:
        raw_content = f.read()

    # ── Remover front-matter YAML (--- ... ---) antes de parsear linha a linha ──
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', raw_content, count=1, flags=re.DOTALL)

    lines = content.splitlines()

    for raw in lines:
        line = raw.rstrip()

        # Linha vazia
        if not line.strip():
            if not in_box:
                story.append(Spacer(1, 6))
            continue

        line = line.strip()

        # BOX abertura
        if line == "[BOX]":
            in_box = True
            buf = []
            continue

        # BOX fechamento
        if line == "[/BOX]":
            story.append(Paragraph(" ".join(buf), BOX))
            in_box = False
            continue

        # Dentro do BOX: acumula texto
        if in_box:
            buf.append(line)
            continue

        # Separador horizontal --- (no corpo, não é front-matter)
        if line == "---":
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.8,
                                    color=LGRAY, spaceAfter=10, spaceBefore=4))
            continue

        # Headings
        if line.startswith("### "):
            story.append(Paragraph(line[4:], H3))
            continue
        if line.startswith("## "):
            story.append(Paragraph(line[3:], H2))
            continue
        if line.startswith("# "):
            story.append(Paragraph(line[2:], H1))
            continue

        # Listas
        if line.startswith("- "):
            story.append(Paragraph("• " + line[2:], LIST))
            continue

        # Imagens [IMG:nome.ext] ou [IMG:img1.ext|img2.ext]
        if line.startswith("[IMG:") and line.endswith("]"):
            names = line[5:-1].strip().split("|")
            md_dir = os.path.dirname(md_path)
            
            loaded_imgs = []
            for name in names:
                name = name.strip()
                candidates = [
                    os.path.join(assets, name),
                    os.path.join(md_dir, name),
                ]
                img_p = next((p for p in candidates if os.path.exists(p)), None)
                if img_p:
                    try:
                        processed = _preprocess_image(img_p)
                        img = Image(processed)
                        loaded_imgs.append(img)
                    except Exception:
                        pass
            
            if not loaded_imgs:
                continue
                
            if len(loaded_imgs) == 1:
                # Uma imagem - Tamanho otimizado para material educacional (menor que a largura total)
                img = loaded_imgs[0]
                img._restrictSize(11 * cm, 10 * cm)  # Largura ~70% da área útil, altura moderada
                img.hAlign = "CENTER"
                story.append(KeepTogether([
                    Spacer(1, 10),
                    img,
                    Spacer(1, 10),
                ]))
            elif len(loaded_imgs) >= 2:
                # Duas imagens lado a lado
                img1 = loaded_imgs[0]
                img2 = loaded_imgs[1]
                # Largura útil = W - 5cm. Vamos colocar um gap de 1cm no meio.
                gap = 1.0 * cm
                col_w = (W - 5 * cm - gap) / 2
                
                img1._restrictSize(col_w, 8 * cm)
                img1.hAlign = "CENTER"
                img2._restrictSize(col_w, 8 * cm)
                img2.hAlign = "CENTER"
                
                # Tabela de 3 colunas: imagem 1, espaço vazio, imagem 2
                t = Table([[img1, "", img2]], colWidths=[col_w, gap, col_w])
                t.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ]))
                
                story.append(KeepTogether([
                    Spacer(1, 10),
                    t,
                    Spacer(1, 10),
                ]))
            continue

        # Parágrafo de texto
        story.append(Paragraph(line, BODY))

    return story


# ════════════════════════════════════════
# EXTRAÇÃO DE META
# ════════════════════════════════════════
def extract_meta(md_path: str) -> dict:
    """
    Extrai title e aula do .md.
    Prioridade: front-matter YAML → primeiro # Heading → nome do arquivo.
    """
    filename = os.path.splitext(os.path.basename(md_path))[0]
    title    = filename
    aula     = "01"
    materia  = "Disciplina"

    num_match = re.search(r'(\d+)', filename)
    if num_match:
        aula = num_match.group(1).zfill(2)

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # Front-matter YAML
    fm = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if fm:
        for line in fm.group(1).splitlines():
            if ':' in line:
                key, _, val = line.partition(':')
                key, val = key.strip().lower(), val.strip()
                if key == 'title':
                    title = val
                if key == 'aula':
                    aula = str(val).zfill(2)
                if key == 'materia':
                    materia = val
        return {"title": title, "aula": aula, "materia": materia}

    # Primeiro # Heading
    h1 = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()

    return {"title": title, "aula": aula, "materia": materia}


# ════════════════════════════════════════
# RENDER INTERNO — BUILD UNIFICADO
# ════════════════════════════════════════
def _render(md_path: str, meta: dict, output_path: str, assets_dir: str) -> str:
    """
    Build direto ao conteúdo — sem capa.
    Margens ABNT ajustadas: Superior 3.5cm | Inferior 3.2cm (para evitar sobreposição)
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=3 * cm, rightMargin=2 * cm,
        topMargin=3.5 * cm, bottomMargin=3.2 * cm,
        pageCompression=1
    )

    story = parse_md(md_path, assets_dir, meta)

    doc.build(
        story,
        onFirstPage=lambda c, d: header_footer(c, d, assets_dir),
        onLaterPages=lambda c, d: header_footer(c, d, assets_dir),
    )
    print(f"  ✅ {os.path.basename(output_path)}")
    return output_path


# ════════════════════════════════════════
# API PÚBLICA — build_from_md
# ════════════════════════════════════════
def build_from_md(md_path: str, output_path: str,
                  assets_dir: str = None, meta: dict = None) -> str:
    """Gera PDF diretamente de um .md (modo escalável)."""
    md_path = os.path.abspath(md_path)
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Arquivo .md não encontrado: {md_path}")

    if meta is None:
        meta = extract_meta(md_path)

    if assets_dir is None:
        assets_dir = os.path.dirname(md_path)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    return _render(md_path, meta, output_path, assets_dir)


# ════════════════════════════════════════
# API PÚBLICA — build (modo projeto legado)
# ════════════════════════════════════════
def build(project: str, base_dir: str = "projects", md_file: str = None):
    """Build a partir de uma pasta projects/aulaXX/."""
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
            raise FileNotFoundError(f"content.md não encontrado: {md_path}")

    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"meta.json não encontrado: {meta_path}")

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    os.makedirs(assets, exist_ok=True)
    return _render(md_path, meta, output, assets)


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
        if idx + 1 < len(sys.argv):
            _md = sys.argv[idx + 1]
    build(_proj, md_file=_md)
