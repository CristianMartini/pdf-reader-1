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
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

import firebase_admin
from firebase_admin import credentials, storage

# ── Base ──
BASE     = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
    PROJECTS = "/tmp/projects"
    # Copy repository pre-existing projects to /tmp/projects so they are available and editable
    os.makedirs(PROJECTS, exist_ok=True)
    repo_projects = os.path.join(BASE, "projects")
    if os.path.isdir(repo_projects):
        for item in os.listdir(repo_projects):
            s_path = os.path.join(repo_projects, item)
            d_path = os.path.join(PROJECTS, item)
            if os.path.isdir(s_path) and not os.path.exists(d_path):
                try:
                    shutil.copytree(s_path, d_path)
                except Exception as e:
                    print(f"Warning: Failed to copy {s_path} to {d_path}: {e}")
else:
    PROJECTS = os.path.join(BASE, "projects")

TMPL_DIR = os.path.join(BASE, "templates")

app = Flask(__name__, template_folder=TMPL_DIR)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB

os.makedirs(PROJECTS, exist_ok=True)


# ── Firebase Initialization ──
firebase_app = None
bucket = None
LAST_SYNCED = {}

def init_firebase():
    global firebase_app, bucket
    if firebase_admin._apps:
        firebase_app = firebase_admin.get_app()
        try:
            bucket = storage.bucket(app=firebase_app)
        except Exception:
            pass
    else:
        cred = None
        service_key_path = os.path.join(BASE, "serviceAccountKey.json")
        
        # 1. Try local serviceAccountKey.json
        if os.path.exists(service_key_path):
            try:
                cred = credentials.Certificate(service_key_path)
                print("🔥 Firebase: Carregando chave de serviceAccountKey.json")
            except Exception as e:
                print(f"❌ Firebase: Erro ao ler serviceAccountKey.json: {e}")
                
        # 2. Try Vercel environment variable
        elif os.environ.get("FIREBASE_CREDENTIALS"):
            try:
                cred_json = json.loads(os.environ.get("FIREBASE_CREDENTIALS"))
                cred = credentials.Certificate(cred_json)
                print("🔥 Firebase: Carregando chave de FIREBASE_CREDENTIALS")
            except Exception as e:
                print(f"❌ Firebase: Erro ao ler FIREBASE_CREDENTIALS env: {e}")
                
        if cred:
            try:
                project_id = None
                if os.path.exists(service_key_path):
                    with open(service_key_path, "r", encoding="utf-8") as f:
                        project_id = json.load(f).get("project_id")
                elif os.environ.get("FIREBASE_CREDENTIALS"):
                    project_id = json.loads(os.environ.get("FIREBASE_CREDENTIALS")).get("project_id")
                
                if project_id:
                    firebase_app = firebase_admin.initialize_app(cred)
                    
                    # Testa os dois domínios possíveis para o bucket (novo padrão e antigo)
                    bucket_name_new = f"{project_id}.firebasestorage.app"
                    bucket_name_old = f"{project_id}.appspot.com"
                    
                    try:
                        # Tenta obter e testar o bucket novo
                        test_bucket = storage.bucket(name=bucket_name_new, app=firebase_app)
                        test_bucket.exists() # Faz chamada de rede leve para validar existência
                        bucket = test_bucket
                        print(f"🔥 Firebase: Conectado com sucesso ao bucket {bucket_name_new}")
                    except Exception:
                        try:
                            # Fallback para o padrão antigo
                            test_bucket = storage.bucket(name=bucket_name_old, app=firebase_app)
                            test_bucket.exists()
                            bucket = test_bucket
                            print(f"🔥 Firebase: Conectado com sucesso ao bucket {bucket_name_old} (Fallback)")
                        except Exception as ex:
                            # Se não houver internet ou se houver falha, assume o novo padrão
                            bucket = storage.bucket(name=bucket_name_new, app=firebase_app)
                            print(f"⚠️ Firebase: Inicializado para {bucket_name_new}, mas validação falhou: {ex}")
                else:
                    print("❌ Firebase: project_id não encontrado nos arquivos de credencial")
            except Exception as e:
                print(f"❌ Firebase: Falha na inicialização: {e}")
        else:
            print("⚠️ Firebase: Nenhuma credencial encontrada. Rodando apenas em modo local.")

init_firebase()


def firebase_list_projects() -> list[str]:
    if not bucket:
        return []
    try:
        blobs = bucket.list_blobs(prefix="projects/", delimiter="/")
        list(blobs) # Consume list to populate prefixes
        prefixes = blobs.prefixes
        projects = []
        for p in prefixes:
            name = p.split("/")[-2]
            if name:
                projects.append(name)
        return projects
    except Exception as e:
        print(f"❌ Firebase: Erro ao listar projetos: {e}")
        return []


def _sync_project_from_firebase(project_name: str, force: bool = False):
    if not bucket:
        return
        
    now = time.time()
    last = LAST_SYNCED.get(project_name, 0)
    
    if not force and (now - last < 30):
        return
        
    try:
        prefix = f"projects/{project_name}/"
        blobs = bucket.list_blobs(prefix=prefix)
        local_proj_dir = os.path.join(PROJECTS, project_name)
        
        for blob in blobs:
            if blob.name.endswith('/'):
                continue
            
            rel_path = os.path.relpath(blob.name, f"projects/{project_name}")
            local_file_path = os.path.join(local_proj_dir, rel_path)
            
            if os.path.exists(local_file_path):
                local_size = os.path.getsize(local_file_path)
                if local_size == blob.size:
                    continue # Already in sync
                    
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            blob.download_to_filename(local_file_path)
            print(f"📥 Firebase: Sincronizado {blob.name} -> {local_file_path}")
            
        LAST_SYNCED[project_name] = now
    except Exception as e:
        print(f"❌ Firebase: Erro ao sincronizar projeto {project_name}: {e}")


def _upload_file_to_firebase(project_name: str, filename: str, is_asset: bool = False):
    if not bucket:
        return
        
    try:
        local_proj_dir = os.path.join(PROJECTS, project_name)
        if is_asset:
            local_path = os.path.join(local_proj_dir, "assets", filename)
            blob_path = f"projects/{project_name}/assets/{filename}"
        else:
            local_path = os.path.join(local_proj_dir, filename)
            blob_path = f"projects/{project_name}/{filename}"
            
        if os.path.isfile(local_path):
            blob = bucket.blob(blob_path)
            blob.upload_from_filename(local_path)
            print(f"📤 Firebase: Upload concluído para {blob_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao fazer upload de {filename}: {e}")


def _delete_file_from_firebase(project_name: str, filename: str, kind: str):
    if not bucket:
        return
        
    try:
        if kind == "img":
            blob_path = f"projects/{project_name}/assets/{filename}"
        else:
            blob_path = f"projects/{project_name}/{filename}"
            
        blob = bucket.blob(blob_path)
        if blob.exists():
            blob.delete()
            print(f"🗑️ Firebase: Excluído {blob_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao excluir {filename} do Firebase: {e}")


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
    project_names = set()
    
    # 1. Get local projects
    if os.path.isdir(PROJECTS):
        for entry in os.scandir(PROJECTS):
            if entry.is_dir() and not entry.name.startswith("."):
                project_names.add(entry.name)
                
    # 2. Get remote Firebase projects
    remote_projs = firebase_list_projects()
    for name in remote_projs:
        project_names.add(name)
        
    for name in sorted(project_names):
        # Sincroniza do Firebase antes de ler a contagem de mds e pdfs
        _sync_project_from_firebase(name)
        pd = _pdir(name)
        mds  = len(glob.glob(os.path.join(pd, "*.md")))
        pdfs = len(glob.glob(os.path.join(pd, "*.pdf")))
        items.append({"name": name, "mds": mds, "pdfs": pdfs})
        
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
    # Sincroniza do Firebase antes de carregar arquivos
    _sync_project_from_firebase(project)
    pd = _pdir(project)
    ad = _adir(project)
    mds  = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(pd, "*.md")))]
    imgs = [os.path.basename(p) for p in sorted(
        glob.glob(os.path.join(ad, "*.*")), key=os.path.getmtime, reverse=True
    )]
    pdfs = [os.path.basename(p) for p in sorted(
        glob.glob(os.path.join(pd, "*.pdf")), key=os.path.getmtime, reverse=True
    )]
    return jsonify(mds=mds, imgs=imgs, pdfs=pdfs)


@app.route("/api/file/<project>/<filename>")
def api_get_file(project, filename):
    # Força sincronização do arquivo individual caso tenha atualizado remoto
    _sync_project_from_firebase(project)
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
    # Upload para o Firebase
    _upload_file_to_firebase(project, filename, is_asset=False)
    return jsonify(ok=True)


@app.route("/api/upload/<project>/<kind>", methods=["POST"])
def api_upload(project, kind):
    files    = request.files.getlist("files")
    dest_dir = _pdir(project) if kind == "md" else _adir(project)
    os.makedirs(dest_dir, exist_ok=True)
    saved = 0
    for f in files:
        if f.filename:
            safe_name = secure_filename(f.filename)
            f.save(os.path.join(dest_dir, safe_name))
            # Upload para o Firebase
            _upload_file_to_firebase(project, safe_name, is_asset=(kind != "md"))
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
        # Excluir do Firebase
        _delete_file_from_firebase(project, filename, kind)
        return jsonify(ok=True)
    return jsonify(ok=False, error="Arquivo não encontrado")


@app.route("/api/clear-images/<project>", methods=["DELETE"])
def api_clear_images(project):
    ad = _adir(project)
    if os.path.isdir(ad):
        for f in os.listdir(ad):
            path = os.path.join(ad, f)
            if os.path.isfile(path):
                os.remove(path)
                # Excluir cada imagem do Firebase
                _delete_file_from_firebase(project, f, "img")
        return jsonify(ok=True)
    return jsonify(ok=False, error="Projeto não encontrado")


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
            pdf_name    = os.path.splitext(fname)[0] + ".pdf"
            output_path = os.path.join(pd, pdf_name)
            if os.path.isfile(md_path):
                meta = extract_meta(md_path)
                build_from_md(md_path, output_path, assets_dir=ad, meta=meta)
                # Upload do PDF gerado para o Firebase
                _upload_file_to_firebase(project, pdf_name, is_asset=False)
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

@app.route("/projects/<project>/assets/<path:filename>")
def serve_asset(project, filename):
    return send_from_directory(_adir(project), filename)

@app.route("/api/instrucoes-ia")
def serve_ai_instructions():
    from flask import Response
    texto = """# DIRETRIZES DE CRIAÇÃO EDUCACIONAL E FORMATAÇÃO (ENGINE PDF EVOLUX)

Este documento estabelece as diretrizes pedagógicas e técnicas OBRIGATÓRIAS para a geração de conteúdo em formato Markdown (.md). Você, como Agente de IA, deve aderir estritamente a estas regras para garantir aderência às normas ABNT e maximizar a retenção do conhecimento.

1. TOM E LINGUAGEM EDUCACIONAL
- O texto deve ser acadêmico, formal, claro e objective.
- PROIBIDO o uso de emojis ou caracteres informais em todo o documento.
- Foque na retenção de conteúdo: utilize parágrafos curtos, introduções claras e conclusões que reforcem o aprendizado (fixação).
- Sempre que possível, termine as seções maiores com uma breve síntese ou pergunta reflexiva para fixação.

2. ESTRUTURA FRONT-MATTER (CABEÇALHO OBRIGATÓRIO)
O arquivo DEVE iniciar exatamente com o bloco abaixo (sem espaços em branco antes):
---
title: Título Oficial da Aula ou Módulo
aula: Número (Ex: 01)
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

5. INSERÇÃO DE IMAGENS (SINTAXE EXCLUSIVA)
- PROIBIDO o uso da sintaxe markdown padrão `![alt](url)`.
- Use EXCLUSIVAMENTE a sintaxe `[IMG:nome_do_arquivo.extensao]`.
- Imagem Única (centralizada, ocupará ~70% da página):
  [IMG:figura1.jpg]
- Imagem Dupla (lado a lado, ideais para quadros comparativos):
  [IMG:antes.jpg|depois.jpg]

6. SEPARADORES HORIZONTAIS
Para criar transições claras entre tópicos distintos, use três traços em uma linha isolada:
---

7. REVISÃO FINAL DE CÓDIGO
- Verifique se não há espaços extras nas tags de imagem.
- Certifique-se da ausência total de emojis.
- Garanta que a hierarquia de títulos faz sentido pedagógico (Introdução -> Desenvolvimento -> Conclusão/Fixação).
"""
    return Response(
        texto,
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment;filename=Instrucoes_Agente_IA_PDF.md"}
    )


def _extract_text_from_pdf(filepath: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(filepath)
    text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
    return text


# ════════════════════════════════════════
# IMPORTAÇÃO E FILA DE PROCESSAMENTO COM IA
# ════════════════════════════════════════
QUEUE_DIR = "/tmp/queue-uploads" if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")) else os.path.join(BASE, "temp_queue_uploads")

@app.route("/api/queue/upload/<project>", methods=["POST"])
def api_queue_upload(project):
    files = request.files.getlist("files")
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    os.makedirs(project_queue_dir, exist_ok=True)
    
    uploaded_files = []
    for f in files:
        if f.filename:
            safe_name = secure_filename(f.filename)
            filepath = os.path.join(project_queue_dir, safe_name)
            f.save(filepath)
            
            ext = os.path.splitext(safe_name)[1].lower().replace(".", "")
            uploaded_files.append({
                "name": f.filename,
                "safe_name": safe_name,
                "type": ext
            })
            
    return jsonify(ok=True, files=uploaded_files)


@app.route("/api/queue/process/<project>", methods=["POST"])
def api_queue_process(project):
    data = request.json or {}
    safe_name = secure_filename(data.get("filename", ""))
    
    if not safe_name:
        return jsonify(ok=False, error="Nome de arquivo inválido")
        
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    filepath = os.path.join(project_queue_dir, safe_name)
    
    if not os.path.isfile(filepath):
        return jsonify(ok=False, error="Arquivo temporário não encontrado no servidor")
        
    try:
        # 1. Extração de texto
        ext = os.path.splitext(safe_name)[1].lower()
        if ext == ".pdf":
            raw_text = _extract_text_from_pdf(filepath)
            if not raw_text.strip():
                return jsonify(ok=False, error="O PDF parece estar vazio ou é uma imagem escaneada sem texto.")
        elif ext in (".md", ".txt"):
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
        else:
            return jsonify(ok=False, error=f"Extensão de arquivo não suportada: {ext}")
            
        # 2. Envio para a IA Gemini (Geração + Revisão)
        from ai.gemini_client import rewrite_content_to_style, review_and_polish_markdown
        draft_markdown = rewrite_content_to_style(raw_text)
        rewritten_markdown = review_and_polish_markdown(draft_markdown)
        
        # 3. Salvar como novo .md no projeto
        dest_filename = os.path.splitext(safe_name)[0] + ".md"
        dest_path = os.path.join(_pdir(project), dest_filename)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(rewritten_markdown)
            
        # Upload do novo markdown gerado pela IA para o Firebase
        _upload_file_to_firebase(project, dest_filename, is_asset=False)
            
        # 4. Remover arquivo temporário
        try:
            os.remove(filepath)
        except Exception:
            pass
            
        return jsonify(ok=True, saved_as=dest_filename)
        
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))


# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═" * 50)
    print("  ⚡ PDF Engine Evolux — Modo Editor Web")
    print("  Abra no navegador:  http://localhost:5000")
    print("═" * 50 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
