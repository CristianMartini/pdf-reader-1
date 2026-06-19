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
import unicodedata
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


def _cover_path(assets: str, filename_stem: str = None):
    if filename_stem:
        for prefix in (f"{filename_stem}_cover", filename_stem, f"cover_{filename_stem}"):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                p = os.path.join(assets, f"{prefix}{ext}")
                if os.path.exists(p):
                    return p
    for n in ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp"):
        p = os.path.join(assets, n)
        if os.path.exists(p):
            return p
    return None


def _find_image_file(name: str, assets_dir: str, md_dir: str) -> str:
    """Busca imagem no assets ou md_dir, com fallback para correspondência aproximada."""
    name = name.strip()
    if not name:
        return None
        
    candidates = [
        os.path.join(assets_dir, name),
        os.path.join(md_dir, name),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            return c
            
    # Fallback: busca aproximada na pasta de assets e md_dir
    def clean_name(n):
        n = os.path.splitext(n)[0].lower()
        n = ''.join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^a-z0-9]', '', n)
        
    target_clean = clean_name(name)
    if not target_clean:
        return None
        
    # Procurar em assets e md_dir
    for search_dir in (assets_dir, md_dir):
        if not search_dir or not os.path.isdir(search_dir):
            continue
        try:
            for filename in os.listdir(search_dir):
                file_path = os.path.join(search_dir, filename)
                if os.path.isfile(file_path):
                    file_clean = clean_name(filename)
                    if target_clean == file_clean or target_clean in file_clean or file_clean in target_clean:
                        print(f"🔍 Match aproximado de imagem: sugerido '{name}' -> encontrado '{filename}'")
                        return file_path
        except Exception as e:
            print(f"Erro na busca aproximada de imagem: {e}")
            
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
                      max_px: int = 2400,
                      quality: int = 95) -> str:
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
                     textColor=NAVY, spaceBefore=22, spaceAfter=14, leading=22)
MATERIA_STYLE = ParagraphStyle("MATERIA_STYLE", fontName=FONT_BOLD, fontSize=18,
                     textColor=NAVY, leading=24, alignment=1)
TITLE_AULA = ParagraphStyle("TITLE_AULA", fontName=FONT_BOLD, fontSize=18,
                     textColor=NAVY, leading=24, alignment=1)
H2  = ParagraphStyle("H2",  fontName=FONT_BOLD, fontSize=14,
                     textColor=NAVY, spaceBefore=18, spaceAfter=12, leading=19)
H3  = ParagraphStyle("H3",  fontName=FONT_BOLD, fontSize=12,
                     textColor=NAVY, spaceBefore=16, spaceAfter=10, leading=16)
H4  = ParagraphStyle("H4",  fontName=FONT_BOLD, fontSize=11.5,
                     textColor=NAVY, spaceBefore=14, spaceAfter=10, leading=15)
H5  = ParagraphStyle("H5",  fontName=FONT_BOLD, fontSize=10.5,
                     textColor=NAVY, spaceBefore=12, spaceAfter=8, leading=14)
BODY = ParagraphStyle("BODY", fontName=FONT_REG, fontSize=12,
                      leading=18, textColor=NAVY, spaceAfter=8, alignment=4)
LIST = ParagraphStyle("LIST", fontName=FONT_REG, fontSize=12,
                      leading=18, textColor=NAVY, leftIndent=20, spaceAfter=4)
BOX  = ParagraphStyle("BOX",  fontName=FONT_REG, fontSize=11,
                      backColor=BOXBG, borderColor=GOLD, borderWidth=4,
                      borderPadding=10, leading=16,
                      textColor=NAVY, spaceAfter=10, spaceBefore=8)
CAPTION = ParagraphStyle("CAPTION", fontName=FONT_REG, fontSize=9,
                           textColor=GRAY, leading=12, alignment=1, spaceAfter=6)
IMG_PLACEHOLDER_STYLE = ParagraphStyle(
    "IMG_PLACEHOLDER_STYLE",
    fontName=FONT_REG,
    fontSize=10.5,
    leading=15,
    textColor=colors.HexColor("#4A5568"),
    backColor=colors.HexColor("#F7FAFC"),
    borderColor=colors.HexColor("#CBD5E0"),
    borderWidth=1,
    borderPadding=12,
    spaceBefore=12,
    spaceAfter=12,
    alignment=1
)
IMG_COL_PLACEHOLDER_STYLE = ParagraphStyle(
    "IMG_COL_PLACEHOLDER_STYLE",
    fontName=FONT_REG,
    fontSize=9.5,
    leading=13,
    textColor=colors.HexColor("#4A5568"),
    backColor=colors.HexColor("#F7FAFC"),
    borderColor=colors.HexColor("#CBD5E0"),
    borderWidth=1,
    borderPadding=8,
    spaceBefore=4,
    spaceAfter=4,
    alignment=1
)


# ════════════════════════════════════════
# CAPA — fiel ao SVG de referência
# ════════════════════════════════════════
def draw_cover(canvas, doc, meta: dict, assets: str):
    canvas.saveState()

    cover = _cover_path(assets, meta.get("filename_stem"))
    if cover:
        canvas.drawImage(cover, 0, 0, width=W, height=H,
                         preserveAspectRatio=False, mask=_logo_mask(cover))
        canvas.restoreState()
        return

    # 1. Fundo NAVY
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

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

    # 8. Título - Renderizado dinamicamente com Paragraph para evitar sobreposição ou quebra da página
    title = meta.get("title", "Sem título")
    if len(title) <= 30:
        font_sz = 44
        leading = 50
    elif len(title) <= 60:
        font_sz = 32
        leading = 38
    else:
        font_sz = 24
        leading = 28

    cover_title_style = ParagraphStyle(
        "CoverTitle",
        fontName=FONT_BOLD,
        fontSize=font_sz,
        leading=leading,
        textColor=colors.white
    )
    p = Paragraph(title, cover_title_style)
    # Limita a largura em 12.5 cm para não colidir com o paralelograma dourado da capa
    w_p, h_p = p.wrap(12.5 * cm, H)
    title_y = H - 534 - 18 - h_p
    p.drawOn(canvas, 2 * cm, title_y)

    canvas.restoreState()


# ════════════════════════════════════════
# CABEÇALHO / RODAPÉ PÁGINAS INTERNAS
# ════════════════════════════════════════
def header_footer(canvas, doc, assets: str):
    """Cabeçalho com logo (sem fundo) + linha dourada. Rod. com paginação centralizada."""
    # Ignora totalmente a primeira página (capa branca)
    if doc.page == 1:
        return

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
    canvas.drawRightString(W - 2 * cm, footer_y - 0.05 * cm, str(doc.page))

    canvas.restoreState()


def _format_inline(text: str) -> str:
    """Converte markdown inline (**bold**, *italic*) para tags do ReportLab de forma robusta e segura."""
    # 1. Escapa '&' que não iniciam entidades conhecidas do XML
    text = re.sub(r'&(?!(amp|lt|gt|quot|apos);)', '&amp;', text)
    
    # 2. Converte Markdown (** e *) para tags HTML usando pilha para garantir aninhamento perfeito (sem tags cruzadas)
    tokens = re.split(r'(\*\*|\*)', text)
    result = []
    stack = []
    for token in tokens:
        if token == '**':
            if 'b' in stack:
                while stack:
                    closed_tag = stack.pop()
                    result.append(f'</{closed_tag}>')
                    if closed_tag == 'b':
                        break
            else:
                result.append('<b>')
                stack.append('b')
        elif token == '*':
            if 'i' in stack:
                while stack:
                    closed_tag = stack.pop()
                    result.append(f'</{closed_tag}>')
                    if closed_tag == 'i':
                        break
            else:
                result.append('<i>')
                stack.append('i')
        else:
            result.append(token)
    while stack:
        closed_tag = stack.pop()
        result.append(f'</{closed_tag}>')
        
    html = "".join(result)
    
    # Remove tags vazias redundantes geradas por tokens markdown residuais
    html = html.replace('<b></b>', '').replace('<i></i>', '')
    
    # 3. Protege tags HTML válidas suportadas nativamente pelo ReportLab
    placeholders = {
        '<b>': '\uE000', '</b>': '\uE001',
        '<i>': '\uE002', '</i>': '\uE003',
        '<sub>': '\uE004', '</sub>': '\uE005',
        '<sup>': '\uE006', '</sup>': '\uE007',
        '<u>': '\uE008', '</u>': '\uE009'
    }
    
    # Substituição case-insensitive
    for tag, placeholder in placeholders.items():
        pattern = re.compile(re.escape(tag), re.IGNORECASE)
        html = pattern.sub(placeholder, html)
        
    # 4. Escapa qualquer '<' e '>' restante na string que possa quebrar o parser XML do ReportLab
    html = html.replace('<', '&lt;').replace('>', '&gt;')
    
    # 5. Restaura as tags permitidas que estavam protegidas
    for tag, placeholder in placeholders.items():
        html = html.replace(placeholder, tag)
        
    # 6. Garante o fechamento automático de tags permitidas se alguma tiver ficado desbalanceada
    for tag in ['b', 'i', 'sub', 'sup', 'u']:
        open_count = html.count(f'<{tag}>') + html.count(f'<{tag.upper()}>')
        close_count = html.count(f'</{tag}>') + html.count(f'</{tag.upper()}>')
        if open_count > close_count:
            html += f'</{tag}>' * (open_count - close_count)
            
    return html

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
    content = re.sub(r'^\s*---\s*\n.*?\n---\s*\n', '', raw_content, count=1, flags=re.DOTALL | re.MULTILINE)

    # Remover sugestões de imagens instrucionais multilinhas (ex: [INSIRA UMA IMAGEM AQUI: ...])
    # Mantém a nossa tag de imagem válida [IMG:...]
    pattern = r'\[\s*(?:INSIRA|INSERIR|IMAGEM|SUGEST[AÃ]O|IMAGE|PHOTO|FIGURA|ILUSTRA[CÇ][AÃ]O|DIAGRAMA)\b[^\]]*\]'
    content = re.sub(pattern, '', content, flags=re.IGNORECASE)

    lines = content.splitlines()

    for raw in lines:
        line = raw.rstrip()

        # Linha vazia
        if not line.strip():
            if not in_box:
                story.append(Spacer(1, 6))
            continue

        line = line.strip()

        # Limpa blockquotes '>' vazados
        if line.startswith(">"):
            line = re.sub(r'^(\s*>)+', '', line).strip()
            if not line:
                continue

        clean_line = line.replace("`", "").strip()

        # BOX abertura
        if clean_line == "[BOX]":
            in_box = True
            buf = []
            continue

        # BOX fechamento
        if clean_line == "[/BOX]":
            story.append(Paragraph(_format_inline(" ".join(buf)), BOX))
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
        if line.startswith("##### "):
            story.append(Paragraph(_format_inline(line[6:]), H5))
            continue
        if line.startswith("#### "):
            story.append(Paragraph(_format_inline(line[5:]), H4))
            continue
        if line.startswith("### "):
            story.append(Paragraph(_format_inline(line[4:]), H3))
            continue
        if line.startswith("## "):
            story.append(Paragraph(_format_inline(line[3:]), H2))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_format_inline(line[2:]), H1))
            continue

        # Listas
        if line.startswith("- "):
            story.append(Paragraph("• " + _format_inline(line[2:]), LIST))
            continue

        # Imagens [IMG:nome.ext] ou [IMG:img1.ext|img2.ext] (suporta descrição opcional depois)
        if line.startswith("[IMG:"):
            bracket_end = line.find("]")
            if bracket_end == -1:
                continue
            
            names_str = line[5:bracket_end].strip()
            names = names_str.split("|")
            
            # Extrai legenda / descrição instrucional
            desc = line[bracket_end + 1:].strip()
            if desc.startswith("(") and desc.endswith(")"):
                desc = desc[1:-1].strip()
                
            md_dir = os.path.dirname(md_path)
            
            if len(names) == 1:
                name_item = names[0].strip()
                img_path = _find_image_file(name_item, assets, md_dir)
                
                if img_path:
                    try:
                        processed = _preprocess_image(img_path)
                        img = Image(processed)
                        img._restrictSize(11 * cm, 10 * cm)
                        img.hAlign = "CENTER"
                        
                        elements = [Spacer(1, 10), img]
                        if desc:
                            elements.append(Spacer(1, 4))
                            elements.append(Paragraph(f"<b>Figura:</b> {desc}", CAPTION))
                        elements.append(Spacer(1, 10))
                        
                        story.append(KeepTogether(elements))
                    except Exception as e:
                        print(f"Erro ao processar imagem real: {e}")
            else:
                # Imagem dupla ou múltipla
                col_elements = []
                gap = 1.0 * cm
                col_w = (W - 5 * cm - gap) / 2
                
                for name_item in names[:2]:
                    name_item = name_item.strip()
                    img_path = _find_image_file(name_item, assets, md_dir)
                    if img_path:
                        try:
                            processed = _preprocess_image(img_path)
                            img = Image(processed)
                            img._restrictSize(col_w, 8 * cm)
                            img.hAlign = "CENTER"
                            col_elements.append(img)
                        except Exception:
                            pass
                
                if not col_elements:
                    continue
                    
                if len(col_elements) == 1:
                    # Apenas uma encontrada - renderiza como única
                    img = col_elements[0]
                    img._restrictSize(11 * cm, 10 * cm)
                    img.hAlign = "CENTER"
                    
                    elements = [Spacer(1, 10), img]
                    if desc:
                        elements.append(Spacer(1, 4))
                        elements.append(Paragraph(f"<b>Figura:</b> {desc}", CAPTION))
                    elements.append(Spacer(1, 10))
                    story.append(KeepTogether(elements))
                else:
                    # Ambas encontradas - renderiza lado a lado
                    t = Table([[col_elements[0], "", col_elements[1]]], colWidths=[col_w, gap, col_w])
                    t.setStyle(TableStyle([
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ]))
                    
                    elements = [Spacer(1, 10), t]
                    if desc:
                        elements.append(Spacer(1, 4))
                        elements.append(Paragraph(f"<b>Figura:</b> {desc}", CAPTION))
                    elements.append(Spacer(1, 10))
                    
                    story.append(KeepTogether(elements))
            continue

        # Parágrafo de texto
        story.append(Paragraph(_format_inline(line), BODY))

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

    # Front-matter YAML (ignora BOM ou espaços invisíveis no início)
    fm = re.search(r'^\s*---\s*\n(.*?)\n---\s*\n', content, re.DOTALL | re.MULTILINE)
    if fm:
        for line in fm.group(1).splitlines():
            if ':' in line:
                key, _, val = line.partition(':')
                key = key.strip().lower()
                # Remove acentos para facilitar o match (ex: matéria -> materia)
                key = ''.join(c for c in unicodedata.normalize('NFD', key) if unicodedata.category(c) != 'Mn')
                val = val.strip()
                
                if key in ('title', 'titulo'):
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
    Build com página de capa e conteúdo interno.
    Margens ABNT ajustadas: Superior 3.5cm | Inferior 3.2cm (para evitar sobreposição)
    """
    if not meta:
        meta = {}
    meta['filename_stem'] = os.path.splitext(os.path.basename(md_path))[0]

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=3 * cm, rightMargin=2 * cm,
        topMargin=3.5 * cm, bottomMargin=3.2 * cm,
        pageCompression=1
    )

    story = parse_md(md_path, assets_dir, meta)

    # Adiciona a página de capa no início
    story.insert(0, PageBreak())
    story.insert(0, Spacer(1, 1))

    doc.build(
        story,
        onFirstPage=lambda c, d: draw_cover(c, d, meta, assets_dir),
        onLaterPages=lambda c, d: header_footer(c, d, assets_dir),
    )
    print(f"  [OK] {os.path.basename(output_path)}")
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
