"""
Imagens originais das aulas — engine/originais.py

Extrai as imagens que aparecem de verdade nas páginas do PDF antigo de uma aula
(fotos e figuras do material didático, que não podem ser trocadas por imagens
novas) e liga cada tag [IMG:...] da aula reescrita à imagem escolhida para o PDF.

Por que olhar onde a imagem é desenhada (operador Do) e não a lista de imagens
da página: o LibreOffice Writer coloca TODAS as imagens do documento nos recursos
de TODAS as páginas. Só o desenho real diz em que página e posição cada uma está.

Formato do arquivo da aula (revisao/<aula>_imagens.json):
  {
    "versao": 1,
    "pdf_original": "aula03.pdf",
    "originais":   [{"arquivo": "p02_01.jpg", "pagina": 2, "paginas": [2], ...}],
    "descartadas": {"fundo": 8, "repetidas": 0, "minusculas": 0, "erros": 0},
    "desenhos":    [{"pagina": 2, "topo_pt": 713.0, "arquivo": "p02_01.jpg"}],
    "escolhas":    {"lesao.png": {"usar": "original", "original": "p02_01.jpg", "travada": true}}
  }
  usar: "original" (imagem do PDF antigo) | "nova" (imagem enviada em assets/) | "nenhuma"
"""

import hashlib
import io
import math
import os
import re
from collections import defaultdict

from pypdf import PdfReader
from pypdf.generic import ContentStream

VERSAO = 1
USOS = ("original", "nova", "nenhuma")

# Heurísticas de descarte (valores em pontos PDF: 1 cm ≈ 28 pt)
AREA_FUNDO = 0.85        # imagem que cobre 85%+ da página
LADO_MIN_PT = 40         # desenhada com menos de ~1,4 cm de lado: ícone, marcador
LADO_MIN_PX = 64         # imagem com menos de 64 px de lado
MAX_IMAGENS = 300        # proteção contra PDFs patológicos
MAX_PROFUNDIDADE = 8     # formulários (Form XObjects) dentro de formulários

_IDENTIDADE = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiplica(m, n):
    """Concatena matrizes PDF [a b c d e f]: resultado = m × n."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + b * c2, a * b2 + b * d2,
            c * a2 + d * c2, c * b2 + d * d2,
            e * a2 + f * c2 + e2, e * b2 + f * d2 + f2)


def _caixa(ctm):
    """Retângulo (x0, y0, x1, y1) ocupado pelo quadrado unitário da imagem na página."""
    a, b, c, d, e, f = ctm
    xs = (e, a + e, c + e, a + c + e)
    ys = (f, b + f, d + f, b + d + f)
    return min(xs), min(ys), max(xs), max(ys)


def _xobjects(recursos):
    try:
        recursos = recursos.get_object() if recursos is not None else None
        xo = recursos.get("/XObject") if recursos is not None else None
        return xo.get_object() if xo is not None else {}
    except Exception:
        return {}


def _desenhos_da_pagina(reader, page):
    """Imagens desenhadas na página, na ordem do conteúdo.
    Cada item: (caminho, ref, ctm, xobject) — caminho é a chave de page.images
    (ex.: "/Im8" ou ["/Fm1", "/Im3"] para imagem dentro de formulário)."""
    saida = []

    def percorre(conteudo, recursos, ctm, caminho, pilha_refs, profundidade):
        if conteudo is None or profundidade > MAX_PROFUNDIDADE:
            return
        try:
            operacoes = conteudo.operations if isinstance(conteudo, ContentStream) \
                else ContentStream(conteudo, reader).operations
        except Exception:
            return
        xobjs = _xobjects(recursos)
        pilha = []
        for operandos, op in operacoes:
            if op == b"q":
                pilha.append(ctm)
            elif op == b"Q":
                ctm = pilha.pop() if pilha else ctm
            elif op == b"cm" and len(operandos) == 6:
                try:
                    ctm = _multiplica(tuple(float(x) for x in operandos), ctm)
                except Exception:
                    pass
            elif op == b"Do" and operandos:
                nome = str(operandos[0])
                ref_obj = xobjs.get(nome) if hasattr(xobjs, "get") else None
                if ref_obj is None:
                    continue
                obj = ref_obj.get_object()
                tipo = obj.get("/Subtype")
                ref = getattr(ref_obj, "idnum", None) or id(obj)
                if tipo == "/Image":
                    saida.append((caminho + [nome], ref, ctm, obj))
                elif tipo == "/Form" and ref not in pilha_refs:
                    matriz = obj.get("/Matrix")
                    try:
                        matriz = matriz.get_object() if matriz is not None else None
                        m = tuple(float(x) for x in matriz) if matriz else _IDENTIDADE
                    except Exception:
                        m = _IDENTIDADE
                    # Formulário sem /Resources próprio herda os da página
                    rec_form = obj.get("/Resources") or recursos
                    percorre(obj, rec_form, _multiplica(m, ctm), caminho + [nome],
                             pilha_refs | {ref}, profundidade + 1)

    percorre(page.get_contents(), page.get("/Resources"), _IDENTIDADE, [], frozenset(), 0)
    return saida


def _filtros(xobj):
    f = xobj.get("/Filter")
    if f is None:
        return []
    f = f.get_object()
    return [str(x) for x in f] if isinstance(f, list) else [str(f)]


def _dados_para_salvar(imagem, xobj):
    """(bytes, extensão) preservando o arquivo original sempre que possível."""
    pil = imagem.image
    ext = (os.path.splitext(imagem.name)[1] or "").lower()
    filtros = _filtros(xobj)
    if (filtros and filtros[-1] == "/DCTDecode" and pil.mode in ("RGB", "L")
            and not any(k in xobj for k in ("/SMask", "/Mask", "/Decode"))):
        # O JPEG gravado no PDF, sem recompressão (imagem.data volta recodificado pelo pypdf)
        return xobj.get_data(), ".jpg"
    if ext == ".png" and pil.mode in ("1", "L", "LA", "RGB", "RGBA"):
        return imagem.data, ".png"
    # CMYK, JPEG 2000, CCITT etc.: converte para um formato que navegador e ReportLab abrem
    if pil.mode == "CMYK" and ext in (".jpg", ".jpeg"):
        buf = io.BytesIO()
        pil.convert("RGB").save(buf, "JPEG", quality=95)
        return buf.getvalue(), ".jpg"
    if pil.mode not in ("1", "L", "LA", "RGB", "RGBA"):
        pil = pil.convert("RGBA" if "A" in pil.mode or pil.mode == "P" else "RGB")
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    return buf.getvalue(), ".png"


def extrair_originais(pdf_path, destino):
    """Salva em `destino` as imagens didáticas do PDF e devolve o índice da aula.

    Descarta fundo de página (papel timbrado), logos/marcas repetidas e ícones.
    Uma imagem reutilizada em várias páginas vira um arquivo só."""
    os.makedirs(destino, exist_ok=True)
    reader = PdfReader(pdf_path)
    n_paginas = len(reader.pages)

    desenhos = []   # (pagina, caminho, ref, caixa, lados_pt, area_rel, altura_pag, xobject)
    for pi, page in enumerate(reader.pages, 1):
        try:
            larg, alt = float(page.mediabox.width), float(page.mediabox.height)
            area_pag = larg * alt or 1.0
            for caminho, ref, ctm, xobj in _desenhos_da_pagina(reader, page):
                caixa = _caixa(ctm)
                a, b, c, d = ctm[:4]
                lados = (math.hypot(a, b), math.hypot(c, d))
                area = (caixa[2] - caixa[0]) * (caixa[3] - caixa[1]) / area_pag
                desenhos.append((pi, caminho, ref, caixa, lados, area, alt, xobj))
        except Exception as e:
            print(f"⚠️ Originais: falha ao ler a página {pi}: {e}")

    paginas_por_ref = defaultdict(set)
    paginas_cheias_por_ref = defaultdict(set)
    for pi, _, ref, _, _, area, _, _ in desenhos:
        paginas_por_ref[ref].add(pi)
        if area >= AREA_FUNDO:
            paginas_cheias_por_ref[ref].add(pi)

    def classifica(ref):
        pags = paginas_por_ref[ref]
        if len(pags) >= max(2, 0.5 * n_paginas) and len(paginas_cheias_por_ref[ref]) >= 0.5 * len(pags):
            return "fundo"
        if len(pags) >= max(3, 0.5 * n_paginas):
            return "repetidas"
        return None

    descartadas = {"fundo": 0, "repetidas": 0, "minusculas": 0, "erros": 0}
    salvas_por_ref = {}
    originais, marcas = [], []

    por_pagina = defaultdict(list)
    for item in desenhos:
        por_pagina[item[0]].append(item)

    for pi in sorted(por_pagina):
        # Ordem de leitura: de cima para baixo e, na mesma altura, da esquerda para a direita
        itens = sorted(por_pagina[pi], key=lambda it: (-round(it[3][3] / 5), it[3][0]))
        ordem = 0
        for _, caminho, ref, caixa, lados, area, alt, xobj in itens:
            motivo = classifica(ref)
            if motivo:
                descartadas[motivo] += 1
                continue
            if ref in salvas_por_ref:
                reg = salvas_por_ref[ref]
                if pi not in reg["paginas"]:
                    reg["paginas"].append(pi)
                marcas.append({"pagina": pi, "topo_pt": round(caixa[3], 1), "arquivo": reg["arquivo"]})
                continue
            if min(lados) < LADO_MIN_PT:
                descartadas["minusculas"] += 1
                continue
            if len(originais) >= MAX_IMAGENS:
                break
            try:
                imagem = reader.pages[pi - 1].images[caminho if len(caminho) > 1 else caminho[0]]
                w_px, h_px = imagem.image.size
                if min(w_px, h_px) < LADO_MIN_PX:
                    descartadas["minusculas"] += 1
                    continue
                dados, ext = _dados_para_salvar(imagem, xobj)
            except Exception as e:
                print(f"⚠️ Originais: imagem {caminho} da página {pi} não pôde ser lida: {e}")
                descartadas["erros"] += 1
                continue

            ordem += 1
            arquivo = f"p{pi:02d}_{ordem:02d}{ext}"
            with open(os.path.join(destino, arquivo), "wb") as fh:
                fh.write(dados)

            prop_img = w_px / h_px if h_px else 0
            prop_pdf = lados[0] / lados[1] if lados[1] else 0
            reg = {
                "arquivo": arquivo,
                "pagina": pi,
                "paginas": [pi],
                "largura_px": w_px,
                "altura_px": h_px,
                "kb": round(len(dados) / 1024),
                "topo_pct": max(0, min(100, round(100 * (1 - caixa[3] / alt)))) if alt else 0,
                "pagina_inteira": area >= AREA_FUNDO,
                # Proporção diferente da exibida: imagem esticada ou recortada no PDF antigo
                "proporcao_diferente": bool(prop_pdf and abs(prop_img - prop_pdf) / prop_pdf > 0.03
                                            and abs(1 / prop_img - prop_pdf) / prop_pdf > 0.03),
                "sha1": hashlib.sha1(dados).hexdigest()[:12],
            }
            salvas_por_ref[ref] = reg
            originais.append(reg)
            marcas.append({"pagina": pi, "topo_pt": round(caixa[3], 1), "arquivo": arquivo})

    return {
        "versao": VERSAO,
        "pdf_original": os.path.basename(pdf_path),
        "paginas": n_paginas,
        "originais": originais,
        "descartadas": descartadas,
        "desenhos": marcas,
    }


def marcadores_por_pagina(indice):
    """{pagina: [(altura_do_topo_pt, arquivo), ...]} de cima para baixo,
    para marcar no texto extraído onde cada imagem original estava."""
    saida = defaultdict(list)
    for d in (indice or {}).get("desenhos", []):
        saida[int(d["pagina"])].append((float(d["topo_pt"]), d["arquivo"]))
    return {p: sorted(v, key=lambda t: -t[0]) for p, v in saida.items()}


# ════════════════════════════════════════
# VÍNCULO ENTRE AS TAGS [IMG] E AS ORIGINAIS
# ════════════════════════════════════════
def slots_da_aula(md_text):
    """Lista as imagens pedidas pela aula: [{"nome", "descricao"}], na ordem do texto.
    Mesmas regras do motor: linha começando com [IMG:a.png] ou [IMG:a.png|b.png]."""
    slots, vistos = [], set()
    for linha in (md_text or "").splitlines():
        linha = linha.strip()
        if not linha.startswith("[IMG:"):
            continue
        fim = linha.find("]")
        if fim == -1:
            continue
        desc = linha[fim + 1:].strip()
        if desc.startswith("(") and desc.endswith(")"):
            desc = desc[1:-1].strip()
        for nome in linha[5:fim].split("|"):
            nome = nome.strip()
            if nome and nome not in vistos:
                vistos.add(nome)
                slots.append({"nome": nome, "descricao": desc})
    return slots


def _blocos_de_prompt(texto):
    """Lê os blocos '### Imagem N: arquivo.png' gerados pelo Gemini (ai/prompt.md)."""
    blocos = []
    for bloco in re.split(r"^### ", texto or "", flags=re.M):
        bloco = bloco.strip()
        if not bloco:
            continue
        titulo = bloco.splitlines()[0].strip()
        if not titulo.lower().startswith("imagem") or ":" not in titulo:
            continue
        original = re.search(r"\*\*Original do PDF\*\*:\s*(.+)", bloco)
        blocos.append({
            "arquivo": titulo.split(":", 1)[1].strip(),
            "original": original.group(1).strip() if original else "",
        })
    return blocos


def escolhas_iniciais(md_text, prompts_text, originais, sensivel=False, escolhas_atuais=None):
    """Monta as escolhas de uma aula recém-gerada a partir do que o Gemini indicou.

    - "Original do PDF: p02_01.jpg" liga a tag a essa original;
    - "Original do PDF: Sim" (sem arquivo) usa a próxima original não usada, na ordem do PDF;
    - escolhas que a pessoa já fez para tags que continuam na aula são mantidas.
    Com `sensivel`, toda tag ligada a uma original fica travada nela."""
    arquivos = [o["arquivo"] for o in originais or []]
    por_radical = {os.path.splitext(a)[0].lower(): a for a in arquivos}
    slots = [s["nome"] for s in slots_da_aula(md_text)]
    escolhas = {}
    atuais = escolhas_atuais or {}
    usados = set()

    for slot in slots:
        if slot in atuais and atuais[slot].get("usar") in USOS:
            escolhas[slot] = dict(atuais[slot])
            if escolhas[slot].get("original"):
                usados.add(escolhas[slot]["original"])

    pendentes_sim = []
    for bloco in _blocos_de_prompt(prompts_text):
        slot = bloco["arquivo"]
        if slot not in slots or slot in escolhas:
            continue
        valor = bloco["original"]
        achado = next((a for a in arquivos if a.lower() in valor.lower()), None)
        if not achado:
            m = re.search(r"p\d{2,3}_\d{2}", valor.lower())
            achado = por_radical.get(m.group(0)) if m else None
        if achado:
            escolhas[slot] = {"usar": "original", "original": achado, "travada": bool(sensivel)}
            usados.add(achado)
        elif valor.lower().startswith("sim"):
            pendentes_sim.append(slot)

    livres = [a for a in arquivos if a not in usados]
    for slot in pendentes_sim:
        if not livres:
            break
        escolhas[slot] = {"usar": "original", "original": livres.pop(0), "travada": bool(sensivel)}
    return escolhas


def limpar_escolhas(escolhas, originais):
    """Valida as escolhas recebidas do navegador."""
    arquivos = {o["arquivo"] for o in originais or []}
    limpas = {}
    for slot, e in (escolhas or {}).items():
        if not isinstance(slot, str) or not isinstance(e, dict):
            continue
        usar = e.get("usar")
        if usar not in USOS:
            continue
        original = e.get("original") if e.get("original") in arquivos else None
        if usar == "original" and not original:
            continue
        limpas[slot[:200]] = {"usar": usar, "original": original, "travada": bool(e.get("travada"))}
    return limpas


def mapa_de_imagens(escolhas, pasta_originais):
    """{tag: caminho do arquivo | None} para o motor de PDF.
    "nova" fica fora do mapa: o motor procura em assets/ como sempre fez."""
    mapa = {}
    for slot, e in (escolhas or {}).items():
        if e.get("usar") == "nenhuma":
            mapa[slot] = None
        elif e.get("usar") == "original" and e.get("original"):
            mapa[slot] = os.path.join(pasta_originais, e["original"])
    return mapa
