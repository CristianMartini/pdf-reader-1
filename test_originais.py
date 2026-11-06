"""
Testes das imagens originais das aulas (engine/originais.py e o uso no motor de PDF).

Os PDFs de teste são gerados aqui mesmo, imitando o que o LibreOffice Writer exporta:
todas as imagens do documento aparecem nos recursos de todas as páginas, com um fundo
de página (papel timbrado) desenhado em todas elas.

Rodar:  python -m pytest test_originais.py   ou   python test_originais.py
"""
import hashlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine.originais import (
    escolhas_iniciais, extrair_originais, limpar_escolhas, mapa_de_imagens,
    marcadores_por_pagina, slots_da_aula,
)

W, H = A4


def _imagens_de_teste(pasta):
    caminhos = {}
    PILImage.new("RGB", (720, 1280), (240, 240, 250)).save(os.path.join(pasta, "fundo.jpg"), quality=80)
    PILImage.new("RGB", (300, 90), (10, 10, 60)).save(os.path.join(pasta, "logo.png"))
    foto = PILImage.new("RGB", (1600, 1000), (180, 40, 40))
    for x in range(0, 1600, 40):  # textura para o JPEG não ficar trivial
        foto.paste((40, 120, 180), (x, 0, x + 20, 1000))
    foto.save(os.path.join(pasta, "foto.jpg"), quality=90)
    esquema = PILImage.new("RGBA", (900, 600), (0, 0, 0, 0))
    esquema.paste((30, 90, 200, 255), (100, 100, 800, 500))
    esquema.save(os.path.join(pasta, "esquema.png"))
    PILImage.new("RGB", (24, 24), (0, 0, 0)).save(os.path.join(pasta, "icone.png"))
    for n in ("fundo.jpg", "logo.png", "foto.jpg", "esquema.png", "icone.png"):
        caminhos[n] = os.path.join(pasta, n)
    return caminhos


def _pdf_estilo_writer(pasta):
    """4 páginas: fundo em todas, logo no topo de todas, foto na pág. 2 (repetida na 4),
    esquema PNG com transparência na pág. 3 junto de um ícone minúsculo."""
    img = _imagens_de_teste(pasta)
    bruto = os.path.join(pasta, "bruto.pdf")
    c = canvas.Canvas(bruto, pagesize=A4)
    for p in range(1, 5):
        c.drawImage(img["fundo.jpg"], 0, 0, width=W, height=H)
        c.drawImage(img["logo.png"], 40, H - 60, width=120, height=36)
        c.drawString(72, H - 120, f"Texto da página {p}, antes da imagem.")
        if p == 2:
            c.drawImage(img["foto.jpg"], 80, 350, width=400, height=250)
        if p == 3:
            c.drawImage(img["esquema.png"], 80, 300, width=300, height=200, mask="auto")
            c.drawImage(img["icone.png"], 60, 280, width=8, height=8)
        if p == 4:
            c.drawImage(img["foto.jpg"], 300, 100, width=200, height=125)
        c.drawString(72, 80, f"Texto da página {p}, depois da imagem.")
        c.showPage()
    c.save()

    # Como no LibreOffice: todas as imagens nos recursos de todas as páginas
    writer = PdfWriter(clone_from=bruto)
    todas = {}
    for page in writer.pages:
        for nome, ref in page["/Resources"]["/XObject"].items():
            todas[nome] = ref
    for page in writer.pages:
        xo = DictionaryObject()
        for nome, ref in todas.items():
            xo[NameObject(nome)] = ref
        page["/Resources"][NameObject("/XObject")] = xo
    final = os.path.join(pasta, "aula_writer.pdf")
    with open(final, "wb") as fh:
        writer.write(fh)
    return final


def _pdf_com_formulario(pasta):
    """Imagem desenhada dentro de um Form XObject, deslocado por translate."""
    img = _imagens_de_teste(pasta)
    caminho = os.path.join(pasta, "formulario.pdf")
    c = canvas.Canvas(caminho, pagesize=A4)
    c.beginForm("caixa")
    c.drawImage(img["foto.jpg"], 0, 0, width=320, height=200)
    c.endForm()
    c.saveState()
    c.translate(100, 400)
    c.doForm("caixa")
    c.restoreState()
    c.showPage()
    c.save()
    return caminho


def test_extrai_so_as_imagens_didaticas():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_estilo_writer(tmp)
        destino = os.path.join(tmp, "originais")
        indice = extrair_originais(pdf, destino)

        arquivos = [o["arquivo"] for o in indice["originais"]]
        assert arquivos == ["p02_01.jpg", "p03_01.png"], arquivos
        assert indice["originais"][0]["paginas"] == [2, 4], "foto reutilizada vira um arquivo só"
        assert indice["descartadas"]["fundo"] == 4
        assert indice["descartadas"]["repetidas"] == 4   # logo em todas as páginas
        assert indice["descartadas"]["minusculas"] == 1  # ícone de 8 pt
        assert sorted(os.listdir(destino)) == arquivos

        # A foto sai idêntica ao JPEG gravado no PDF (sem recompressão)
        reader = PdfReader(pdf)
        foto = next(ref.get_object() for ref in reader.pages[1]["/Resources"]["/XObject"].values()
                    if ref.get_object().get("/Width") == 1600)
        assert "/DCTDecode" in str(foto["/Filter"])
        with open(os.path.join(destino, "p02_01.jpg"), "rb") as fh:
            assert hashlib.sha1(fh.read()).digest() == hashlib.sha1(foto.get_data()).digest()

        # O PNG mantém a transparência
        with PILImage.open(os.path.join(destino, "p03_01.png")) as im:
            assert im.mode == "RGBA" and im.size == (900, 600)

        marcas = marcadores_por_pagina(indice)
        assert [a for _, a in marcas[2]] == ["p02_01.jpg"]
        assert [a for _, a in marcas[4]] == ["p02_01.jpg"]
        assert 1 not in marcas


def test_imagem_dentro_de_formulario():
    with tempfile.TemporaryDirectory() as tmp:
        indice = extrair_originais(_pdf_com_formulario(tmp), os.path.join(tmp, "originais"))
        assert [o["arquivo"] for o in indice["originais"]] == ["p01_01.jpg"]
        # Topo da imagem: 400 + 200 pt a partir da base da página
        assert indice["desenhos"][0]["topo_pt"] == 600.0
        assert indice["originais"][0]["proporcao_diferente"] is False


def test_texto_marca_onde_ficava_cada_imagem():
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        import web
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_estilo_writer(tmp)
        indice = extrair_originais(pdf, os.path.join(tmp, "originais"))
        with contextlib.redirect_stdout(io.StringIO()):
            com_marcas = web._extract_text_from_pdf(pdf, marcadores_por_pagina(indice))
            sem_marcas = web._extract_text_from_pdf(pdf)
        linhas = [l for l in com_marcas.splitlines() if l.strip()]
        i = linhas.index("[IMAGEM ORIGINAL: p02_01.jpg]")
        assert "página 2, antes" in linhas[i - 1] and "página 2, depois" in linhas[i + 1]
        assert "[IMAGEM ORIGINAL: p03_01.png]" in linhas
        # Fora as marcas, o texto é o mesmo de antes
        assert [l for l in linhas if not l.startswith("[IMAGEM ORIGINAL:")] == \
               [l for l in sem_marcas.splitlines() if l.strip()]


def test_escolhas_iniciais_a_partir_dos_prompts():
    md = ("---\ntitle: T\n---\n# T\n\n[IMG:foice.png] (Foice)\n\n[IMG:mosca_a.png|mosca_b.png] (Moscas)\n\n"
          "[IMG:esquema.png] (Esquema novo)\n")
    prompts = ("### Imagem 1: foice.png\n- **Original do PDF**: p02_01.jpg\n\n"
               "### Imagem 2: mosca_a.png\n- **Original do PDF**: Sim\n\n"
               "### Imagem 3: mosca_b.png\n- **Original do PDF**: Sim (existe no PDF)\n\n"
               "### Imagem 4: esquema.png\n- **Original do PDF**: Não (imagem nova)\n\n"
               "### Capa: capa_aula_03.png\n- **Prompt para o ChatGPT**:\n```\nx\n```\n")
    originais = [{"arquivo": "p02_01.jpg"}, {"arquivo": "p04_01.jpg"}, {"arquivo": "p05_01.jpg"}]

    assert [s["nome"] for s in slots_da_aula(md)] == ["foice.png", "mosca_a.png", "mosca_b.png", "esquema.png"]
    e = escolhas_iniciais(md, prompts, originais, sensivel=True)
    assert e["foice.png"] == {"usar": "original", "original": "p02_01.jpg", "travada": True}
    assert e["mosca_a.png"]["original"] == "p04_01.jpg"   # "Sim": próxima original livre, na ordem do PDF
    assert e["mosca_b.png"]["original"] == "p05_01.jpg"
    assert "esquema.png" not in e                          # imagem nova: fica com assets/

    # Escolha feita pela pessoa é mantida ao reprocessar
    atual = {"foice.png": {"usar": "nenhuma", "original": None, "travada": False}}
    e2 = escolhas_iniciais(md, prompts, originais, escolhas_atuais=atual)
    assert e2["foice.png"]["usar"] == "nenhuma"
    assert e2["mosca_a.png"]["original"] == "p02_01.jpg"   # p02_01 ficou livre


def test_limpar_escolhas_recusa_dados_invalidos():
    originais = [{"arquivo": "p02_01.jpg"}]
    limpas = limpar_escolhas({
        "ok.png": {"usar": "original", "original": "p02_01.jpg", "travada": 1},
        "fora.png": {"usar": "original", "original": "../../etc/passwd"},
        "estranho.png": {"usar": "apagar_tudo"},
        "sem.png": {"usar": "nenhuma"},
        "lista.png": ["original"],
    }, originais)
    assert limpas == {
        "ok.png": {"usar": "original", "original": "p02_01.jpg", "travada": True},
        "sem.png": {"usar": "nenhuma", "original": None, "travada": False},
    }


def test_motor_usa_a_escolha_e_avisa_imagem_faltando():
    import contextlib
    from engine.template import build_from_md
    with tempfile.TemporaryDirectory() as tmp:
        img = _imagens_de_teste(tmp)
        assets = os.path.join(tmp, "assets")
        os.makedirs(assets)
        PILImage.new("RGB", (400, 300), (0, 120, 0)).save(os.path.join(assets, "nova.png"))
        md = os.path.join(tmp, "aula.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("---\ntitle: Teste\naula: 01\nmateria: Teste\n---\n# Teste\n\nTexto.\n\n"
                     "[IMG:nova.png] (A original escolhida substitui esta)\n\n"
                     "[IMG:retirada.png] (Sem imagem por escolha)\n\n"
                     "[IMG:sumiu.png] (Sem arquivo nenhum)\n")
        escolhas = {"nova.png": {"usar": "original", "original": "foto.jpg"},
                    "retirada.png": {"usar": "nenhuma"}}
        mapa = mapa_de_imagens(escolhas, tmp)
        faltando = []
        saida = os.path.join(tmp, "aula.pdf")
        with contextlib.redirect_stdout(io.StringIO()):
            build_from_md(md, saida, assets_dir=assets, image_map=mapa, faltando=faltando)
        assert faltando == ["sumiu.png"]
        # (o motor também desenha o logo padrão no cabeçalho)
        tamanhos = [im.image.size for p in PdfReader(saida).pages for im in p.images]
        assert (1600, 1000) in tamanhos, tamanhos   # a foto original escolhida
        assert (400, 300) not in tamanhos, tamanhos  # a imagem nova de mesmo nome não entrou

        # Sem mapa, continua igual a antes: usa a imagem de assets/
        with contextlib.redirect_stdout(io.StringIO()):
            build_from_md(md, saida, assets_dir=assets)
        tamanhos = [im.image.size for p in PdfReader(saida).pages for im in p.images]
        assert (400, 300) in tamanhos and (1600, 1000) not in tamanhos, tamanhos
        assert os.path.isfile(img["foto.jpg"])


if __name__ == "__main__":
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in testes:
        t()
        print(f"✅ {t.__name__}")
    print(f"✅ {len(testes)} testes passaram")
