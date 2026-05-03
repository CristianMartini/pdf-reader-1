"""
PDF Engine Evolux — web.py
Servidor Flask com arquitetura orientada a projetos.

Estrutura:
  projects/
    <nome-do-projeto>/
      assets/       ← imagens e assets do projeto
      aula01.md     ← documentos markdown
      aula01.pdf    ← PDFs gerados (ficam no mesmo projeto)
"""

import os
import glob
import json
import shutil
import traceback
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# ── Base ──
BASE     = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.join(BASE, "projects")
TMPL_DIR = os.path.join(BASE, "templates")

app = Flask(__name__, template_folder=TMPL_DIR)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB

os.makedirs(PROJECTS, exist_ok=True)


# ── Helpers ──
def _pdir(project: str) -> str:
    return os.path.join(PROJECTS, secure_filename(project))

def _adir(project: str) -> str:
    return os.path.join(_pdir(project), "assets")


# ════════════════════════════════════════
# FRONTEND
# ════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


# ════════════════════════════════════════
# PROJETOS
# ════════════════════════════════════════
@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    items = []
    if os.path.isdir(PROJECTS):
        for entry in sorted(os.scandir(PROJECTS), key=lambda e: e.name):
            if entry.is_dir():
                mds  = len(glob.glob(os.path.join(entry.path, "*.md")))
                pdfs = len(glob.glob(os.path.join(entry.path, "*.pdf")))
                items.append({"name": entry.name, "mds": mds, "pdfs": pdfs})
    return jsonify(projects=items)


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify(ok=False, error="Nome inválido")
    safe = secure_filename(name)
    if not safe:
        return jsonify(ok=False, error="Nome contém apenas caracteres inválidos")
    pd = _pdir(safe)
    os.makedirs(pd, exist_ok=True)
    os.makedirs(_adir(safe), exist_ok=True)
    return jsonify(ok=True, name=safe)


@app.route("/api/projects/<project>", methods=["DELETE"])
def api_delete_project(project):
    pd = _pdir(project)
    if os.path.isdir(pd):
        shutil.rmtree(pd)
        return jsonify(ok=True)
    return jsonify(ok=False, error="Projeto não encontrado")


# ════════════════════════════════════════
# ARQUIVOS DO PROJETO
# ════════════════════════════════════════
@app.route("/api/files/<project>")
def api_files(project):
    pd = _pdir(project)
    ad = _adir(project)
    mds  = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(pd, "*.md")))]
    imgs = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(ad, "*.*")))]
    pdfs = [os.path.basename(p) for p in sorted(
        glob.glob(os.path.join(pd, "*.pdf")), key=os.path.getmtime, reverse=True
    )]
    return jsonify(mds=mds, imgs=imgs, pdfs=pdfs)


@app.route("/api/file/<project>/<filename>")
def api_get_file(project, filename):
    path = os.path.join(_pdir(project), secure_filename(filename))
    if not os.path.isfile(path):
        return jsonify(ok=False, error="Arquivo não encontrado")
    from engine.template import extract_meta
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    meta = extract_meta(path)
    return jsonify(ok=True, content=content, meta=meta)


@app.route("/api/save/<project>", methods=["POST"])
def api_save(project):
    data     = request.json or {}
    filename = secure_filename(data.get("filename", ""))
    content  = data.get("content", "")
    if not filename:
        return jsonify(ok=False, error="Nome de arquivo inválido")
    pd = _pdir(project)
    os.makedirs(pd, exist_ok=True)
    with open(os.path.join(pd, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify(ok=True)


@app.route("/api/upload/<project>/<kind>", methods=["POST"])
def api_upload(project, kind):
    files    = request.files.getlist("files")
    dest_dir = _pdir(project) if kind == "md" else _adir(project)
    os.makedirs(dest_dir, exist_ok=True)
    saved = 0
    for f in files:
        if f.filename:
            f.save(os.path.join(dest_dir, secure_filename(f.filename)))
            saved += 1
    return jsonify(ok=True, saved=saved)


@app.route("/api/delete/<project>/<kind>/<filename>", methods=["DELETE"])
def api_delete_file(project, kind, filename):
    filename = secure_filename(filename)
    if kind == "md":
        path = os.path.join(_pdir(project), filename)
    elif kind == "img":
        path = os.path.join(_adir(project), filename)
    elif kind == "pdf":
        path = os.path.join(_pdir(project), filename)
    else:
        return jsonify(ok=False, error="Tipo inválido")
    if os.path.isfile(path):
        os.remove(path)
        return jsonify(ok=True)
    return jsonify(ok=False, error="Arquivo não encontrado")


# ════════════════════════════════════════
# GERAÇÃO DE PDF
# ════════════════════════════════════════
@app.route("/api/generate", methods=["POST"])
def api_generate():
    data    = request.json or {}
    project = data.get("project", "")
    files   = data.get("files", [])

    if not project:
        return jsonify(ok=False, error="Selecione um projeto")
    if not files:
        return jsonify(ok=False, error="Nenhum arquivo selecionado")

    from engine.template import build_from_md, extract_meta

    pd      = _pdir(project)
    ad      = _adir(project)
    results = []

    try:
        for fname in files:
            md_path     = os.path.join(pd, secure_filename(fname))
            output_path = os.path.join(pd, os.path.splitext(fname)[0] + ".pdf")
            if os.path.isfile(md_path):
                meta = extract_meta(md_path)
                build_from_md(md_path, output_path, assets_dir=ad, meta=meta)
                results.append(os.path.basename(output_path))
        return jsonify(ok=True, result=results)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))


# ════════════════════════════════════════
# SERVIR PDFs E INSTRUÇÕES
# ════════════════════════════════════════
@app.route("/projects/<project>/pdf/<path:filename>")
def serve_pdf(project, filename):
    return send_from_directory(_pdir(project), filename)

@app.route("/api/instrucoes-ia")
def serve_ai_instructions():
    from flask import Response
    texto = """# DIRETRIZES DE CRIAÇÃO EDUCACIONAL E FORMATAÇÃO (ENGINE PDF EVOLUX)

Este documento estabelece as diretrizes pedagógicas e técnicas OBRIGATÓRIAS para a geração de conteúdo em formato Markdown (.md). 

Sua Persona: Você é um Especialista em Áreas Forenses e Professor de Curso Superior. Sua didática é impecável, rigorosa do ponto de vista científico, mas acessível e focada na excelência acadêmica.

Você deve aderir estritamente a estas regras para garantir aderência às normas ABNT e maximizar a retenção do conhecimento:

1. TOM E LINGUAGEM EDUCACIONAL
- O texto deve ser acadêmico, formal, claro e objetivo (nível superior).
- ORTOGRAFIA IMPECÁVEL: Você deve gerar o texto com a acentuação e pontuação perfeitas do Português do Brasil. Certifique-se de que todas as frases terminem com a pontuação correta (ponto final) e que não haja ausência de acentos (ex: use "Histórico" em vez de "Historico", "Introdução" em vez de "Introducao").
- PROIBIDO o uso de emojis ou caracteres informais em todo o documento.
- Foque na retenção de conteúdo: utilize parágrafos curtos, introduções claras e conclusões que reforcem o aprendizado (fixação).
- Sempre que possível, termine as seções maiores com uma breve síntese ou pergunta reflexiva para fixação.

2. ESTRUTURA FRONT-MATTER (CABEÇALHO OBRIGATÓRIO)
O arquivo DEVE iniciar exatamente com o bloco abaixo (sem espaços em branco antes):
---
title: Título Oficial da Aula ou Módulo
aula: Número (Ex: 01)
materia: Nome da Disciplina (Ex: Perito Criminal)
---

3. FORMATAÇÃO ABNT E HIERARQUIA DE TEXTO
- Título principal (Apenas um): `# Titulo Principal`
- Subtítulos: `## Subtitulo` ou `### Subtitulo menor`.
- Parágrafos: Não adicione espaços em branco no início das linhas (sem recuo manual). Separe os parágrafos sempre com exatamente UMA linha em branco.
- Alinhamento: O motor PDF aplicará o alinhamento justificado automaticamente. Não tente forçar formatações de espaço.
- Listas: Utilize o traço padrão: `- Item da lista`.

4. DESTAQUES PARA FIXAÇÃO DE CONTEÚDO (BOX)
Utilize blocos de destaque para conceitos-chave, resumos de fixação ou definições importantes.
Sintaxe isolada:
[BOX]
Conceito-Chave: A necropsia é uma ferramenta de vigilância epidemiológica essencial.
[/BOX]

5. SUGESTÃO DE IMAGENS DIDÁTICAS (PLACEHOLDERS)
Você não tem os nomes dos arquivos de imagem, portanto você DEVE sugerir ao usuário exatamente ONDE uma imagem faria sentido e QUAL deveria ser o seu conteúdo.
- PROIBIDO o uso da sintaxe markdown padrão `![alt](url)`.
- Use EXCLUSIVAMENTE este formato de marcação em uma linha isolada:
  [INSIRA UMA IMAGEM AQUI: "Descreva com detalhes o que a imagem deve mostrar. Ex: Médico legista examinando cadáver"]
- O usuário humano substituirá essa marcação pelas imagens reais depois.

6. SEPARADORES HORIZONTAIS
Para criar transições claras entre tópicos distintos, use três traços em uma linha isolada:
---

7. REVISÃO FINAL DE CÓDIGO
- Certifique-se da ausência total de emojis.
- Garanta que a hierarquia de títulos faz sentido pedagógico (Introdução -> Desenvolvimento -> Conclusão/Fixação).
"""
    return Response(
        texto,
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment;filename=Instrucoes_Agente_IA_PDF.md"}
    )


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═" * 50)
    print("  ⚡ PDF Engine Evolux — Modo Editor Web")
    print("  Abra no navegador:  http://localhost:5000")
    print("═" * 50 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
