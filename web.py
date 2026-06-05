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

# ── Load .env file manually if exists ──
env_path = os.path.join(BASE, ".env")
if os.path.exists(env_path):
    try:
        import re
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.splitlines()
        current_key = None
        current_value_lines = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            
            match = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.*)$', line)
            if match:
                if current_key:
                    val = "\n".join(current_value_lines).strip()
                    if len(val) >= 2 and (
                        (val.startswith('"') and val.endswith('"')) or
                        (val.startswith("'") and val.endswith("'"))
                    ):
                        val = val[1:-1]
                    os.environ[current_key] = val
                
                current_key = match.group(1)
                current_value_lines = [match.group(2)]
            else:
                if current_key:
                    current_value_lines.append(line)
        
        if current_key:
            val = "\n".join(current_value_lines).strip()
            if len(val) >= 2 and (
                (val.startswith('"') and val.endswith('"')) or
                (val.startswith("'") and val.endswith("'"))
            ):
                val = val[1:-1]
            os.environ[current_key] = val
    except Exception as e:
        print(f"❌ Error loading .env file: {e}")

def is_vercel():
    return (
        os.environ.get("VERCEL") == "1"
        or os.environ.get("VERCEL_ENV") is not None
        or not os.access(BASE, os.W_OK)
    )

if is_vercel():
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
_bucket_resolved = False
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
        project_id = None
        service_key_path = os.path.join(BASE, "serviceAccountKey.json")
        
        # 1. Try environment variable (either from .env locally or Vercel dashboard in production)
        if os.environ.get("FIREBASE_CREDENTIALS"):
            try:
                cred_json = json.loads(os.environ.get("FIREBASE_CREDENTIALS"))
                cred = credentials.Certificate(cred_json)
                project_id = cred_json.get("project_id")
                print("🔥 Firebase: Carregando chave de FIREBASE_CREDENTIALS")
            except Exception as e:
                print(f"❌ Firebase: Erro ao ler FIREBASE_CREDENTIALS env: {e}")
                
        # 2. Try local serviceAccountKey.json file
        elif os.path.exists(service_key_path):
            try:
                cred = credentials.Certificate(service_key_path)
                with open(service_key_path, "r", encoding="utf-8") as f:
                    project_id = json.load(f).get("project_id")
                print("🔥 Firebase: Carregando chave de serviceAccountKey.json")
            except Exception as e:
                print(f"❌ Firebase: Erro ao ler serviceAccountKey.json: {e}")
                
        if cred:
            try:
                if project_id:
                    firebase_app = firebase_admin.initialize_app(cred)
                    
                    # Inicializa o bucket padrão sem fazer chamadas de rede no startup
                    bucket_name = f"{project_id}.firebasestorage.app"
                    bucket = storage.bucket(name=bucket_name, app=firebase_app)
                    print(f"🔥 Firebase: Inicializado com bucket padrão {bucket_name}")
                else:
                    print("❌ Firebase: project_id não encontrado nos arquivos de credencial")
            except Exception as e:
                print(f"❌ Firebase: Falha na inicialização: {e}")
        else:
            print("⚠️ Firebase: Nenhuma credencial encontrada. Rodando apenas em modo local.")

init_firebase()

def configure_cors(b):
    try:
        b.cors = [
            {
                "origin": ["*"],
                "method": ["GET", "PUT", "POST", "DELETE", "OPTIONS"],
                "responseHeader": ["Content-Type", "x-goog-resumable"],
                "maxAgeSeconds": 3600
            }
        ]
        b.update()
        print("🔥 Firebase: CORS configurado no bucket")
    except Exception as e:
        print(f"⚠️ Firebase: Não foi possível atualizar CORS no bucket: {e}")

def get_bucket():
    global bucket, _bucket_resolved
    if not bucket or _bucket_resolved:
        return bucket
        
    # Realiza a validação/resolução do bucket de forma preguiçosa (lazy)
    try:
        bucket.exists() # Testa o padrão (.firebasestorage.app)
        _bucket_resolved = True
        print(f"🔥 Firebase: Bucket validado com sucesso: {bucket.name}")
        configure_cors(bucket)
    except Exception as e:
        # Se falhar, tenta o fallback (.appspot.com)
        if bucket.name.endswith(".firebasestorage.app"):
            old_name = bucket.name.replace(".firebasestorage.app", ".appspot.com")
            try:
                fallback_bucket = storage.bucket(name=old_name, app=firebase_app)
                fallback_bucket.exists()
                bucket = fallback_bucket
                _bucket_resolved = True
                print(f"🔥 Firebase: Fallback para o bucket {old_name} com sucesso")
                configure_cors(bucket)
            except Exception as ex:
                print(f"⚠️ Firebase: Validação do bucket falhou em ambos os formatos. Usando padrão {bucket.name}. Erro: {ex}")
                _bucket_resolved = True
    return bucket


def firebase_list_projects() -> list[str]:
    b = get_bucket()
    if not b:
        return []
    try:
        blobs = b.list_blobs(prefix="projects/", delimiter="/")
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


def _firebase_count_files(project_name: str) -> dict:
    """Count md and pdf files in a Firebase project WITHOUT downloading."""
    b = get_bucket()
    if not b:
        return {"mds": 0, "pdfs": 0}
    try:
        prefix = f"projects/{project_name}/"
        blobs = list(b.list_blobs(prefix=prefix))
        mds = sum(1 for bl in blobs if bl.name.endswith(".md") and "/assets/" not in bl.name)
        pdfs = sum(1 for bl in blobs if bl.name.endswith(".pdf") and "/assets/" not in bl.name)
        return {"mds": mds, "pdfs": pdfs}
    except Exception:
        return {"mds": 0, "pdfs": 0}


def _sync_project_from_firebase(project_name: str, force: bool = False):
    b = get_bucket()
    if not b:
        return
        
    now = time.time()
    last = LAST_SYNCED.get(project_name, 0)
    
    if not force and (now - last < 120):
        return
        
    try:
        prefix = f"projects/{project_name}/"
        blobs = b.list_blobs(prefix=prefix)
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
    b = get_bucket()
    if not b:
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
            blob = b.blob(blob_path)
            blob.upload_from_filename(local_path)
            print(f"📤 Firebase: Upload concluído para {blob_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao fazer upload de {filename}: {e}")


def _delete_file_from_firebase(project_name: str, filename: str, kind: str):
    b = get_bucket()
    if not b:
        return
        
    try:
        if kind == "img":
            blob_path = f"projects/{project_name}/assets/{filename}"
        else:
            blob_path = f"projects/{project_name}/{filename}"
            
        blob = b.blob(blob_path)
        if blob.exists():
            blob.delete()
            print(f"🗑️ Firebase: Excluído {blob_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao excluir {filename} do Firebase: {e}")


def _delete_project_from_firebase(project_name: str):
    """Exclui todos os blobs de um projeto no Firebase Storage."""
    b = get_bucket()
    if not b:
        return
    try:
        prefix = f"projects/{project_name}/"
        blobs = list(b.list_blobs(prefix=prefix))
        if blobs:
            for blob in blobs:
                blob.delete()
            print(f"🗑️ Firebase: Excluídos {len(blobs)} arquivos do projeto {project_name}")
        # Limpar cache de sincronização
        LAST_SYNCED.pop(project_name, None)
    except Exception as e:
        print(f"❌ Firebase: Erro ao excluir projeto {project_name}: {e}")


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
    
    # 1. Get remote Firebase projects first (fast, single network call)
    remote_projs = firebase_list_projects()
    for name in remote_projs:
        project_names.add(name)
        
    # 2. Get local projects & upload .keep if not on Firebase
    if os.path.isdir(PROJECTS):
        for entry in os.scandir(PROJECTS):
            if entry.is_dir() and not entry.name.startswith("."):
                project_names.add(entry.name)
                # Se o projeto local ainda não existe no Firebase, cria/garante .keep e faz upload
                if entry.name not in remote_projs:
                    keep_path = os.path.join(entry.path, ".keep")
                    try:
                        if not os.path.exists(keep_path):
                            with open(keep_path, "w", encoding="utf-8") as f:
                                f.write("")
                        _upload_file_to_firebase(entry.name, ".keep", is_asset=False)
                    except Exception:
                        pass
        
    for name in sorted(project_names):
        # Conta de arquivos: prioriza disco local, com fallback para Firebase metadata (sem download)
        pd = _pdir(name)
        if os.path.isdir(pd):
            mds  = len(glob.glob(os.path.join(pd, "*.md")))
            pdfs = len(glob.glob(os.path.join(pd, "*.pdf")))
        else:
            counts = _firebase_count_files(name)
            mds = counts["mds"]
            pdfs = counts["pdfs"]
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
    
    # Criar e fazer o upload do arquivo .keep para garantir persistência no Firebase Storage
    keep_path = os.path.join(pd, ".keep")
    try:
        with open(keep_path, "w", encoding="utf-8") as f:
            f.write("")
        _upload_file_to_firebase(safe, ".keep", is_asset=False)
    except Exception as e:
        print(f"⚠️ Firebase: Não foi possível subir o .keep inicial: {e}")
        
    return jsonify(ok=True, name=safe)


@app.route("/api/projects/<project>", methods=["DELETE"])
def api_delete_project(project):
    pd = _pdir(project)
    if os.path.isdir(pd):
        shutil.rmtree(pd)
    # Excluir todos os arquivos do projeto no Firebase (mesmo que o diretório local não exista)
    _delete_project_from_firebase(project)
    return jsonify(ok=True)


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


@app.route("/api/upload/signed-url", methods=["POST"])
def api_upload_signed_url():
    if not get_bucket():
        return jsonify(ok=False, firebase_active=False, error="Firebase inativo ou não configurado")

    data = request.json or {}
    project = data.get("project", "")
    filename = data.get("filename", "")
    content_type = data.get("contentType", "")
    kind = data.get("kind", "")

    if not project or not filename or not kind:
        return jsonify(ok=False, error="Parâmetros inválidos")

    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify(ok=False, error="Nome de arquivo inválido")

    # Caminho do blob dependendo do tipo
    if kind == "md":
        blob_path = f"projects/{secure_filename(project)}/{safe_name}"
    elif kind == "img":
        blob_path = f"projects/{secure_filename(project)}/assets/{safe_name}"
    elif kind == "queue":
        blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
    else:
        return jsonify(ok=False, error="Tipo de upload inválido")

    try:
        from datetime import timedelta
        b = get_bucket()
        blob = b.blob(blob_path)
        
        # Gerando signed URL v4 com PUT
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type=content_type
        )
        return jsonify(ok=True, firebase_active=True, url=url, blob_path=blob_path, safe_name=safe_name)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, firebase_active=True, error=str(e))


@app.route("/api/upload/confirm/<project>/<kind>", methods=["POST"])
def api_upload_confirm(project, kind):
    data = request.json or {}
    filename = secure_filename(data.get("filename", ""))
    
    if not filename:
        return jsonify(ok=False, error="Nome de arquivo inválido")
        
    b = get_bucket()
    if not b:
        return jsonify(ok=False, error="Firebase não está ativo neste ambiente")

    safe_proj = secure_filename(project)
    
    if kind == "md":
        blob_path = f"projects/{safe_proj}/{filename}"
        local_path = os.path.join(_pdir(safe_proj), filename)
    elif kind == "img":
        blob_path = f"projects/{safe_proj}/assets/{filename}"
        local_path = os.path.join(_adir(safe_proj), filename)
    else:
        return jsonify(ok=False, error="Tipo inválido")

    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob = b.blob(blob_path)
        if blob.exists():
            blob.download_to_filename(local_path)
            print(f"📥 Firebase: Download pós-upload concluído para {local_path}")
            return jsonify(ok=True)
        else:
            return jsonify(ok=False, error="Blob não encontrado no storage remoto")
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))


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
QUEUE_DIR = "/tmp/queue-uploads" if is_vercel() else os.path.join(BASE, "temp_queue_uploads")

@app.route("/api/queue/upload/<project>", methods=["POST"])
def api_queue_upload(project):
    files = request.files.getlist("files")
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    os.makedirs(project_queue_dir, exist_ok=True)
    
    uploaded_files = []
    b = get_bucket()
    for f in files:
        if f.filename:
            safe_name = secure_filename(f.filename)
            filepath = os.path.join(project_queue_dir, safe_name)
            f.save(filepath)
            
            # Se o Firebase estiver ativo, salvar uma cópia temporária na nuvem.
            # Isso é crucial no Vercel (serverless) onde instâncias são efêmeras
            # e a fila de processamento pode cair em outro container sem o arquivo local.
            if b:
                try:
                    blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                    blob = b.blob(blob_path)
                    blob.upload_from_filename(filepath)
                    print(f"📤 Firebase: Backup temporário concluído para {blob_path}")
                except Exception as ex:
                    print(f"⚠️ Firebase: Falha no backup temporário: {ex}")
            
            ext = os.path.splitext(safe_name)[1].lower().replace(".", "")
            uploaded_files.append({
                "name": f.filename,
                "safe_name": safe_name,
                "type": ext
            })
            
    return jsonify(ok=True, files=uploaded_files)


@app.route("/api/queue/confirm/<project>", methods=["POST"])
def api_queue_confirm(project):
    data = request.json or {}
    files_info = data.get("files", [])
    
    if not files_info:
        return jsonify(ok=False, error="Nenhum arquivo especificado")
        
    b = get_bucket()
    if not b:
        return jsonify(ok=False, error="Firebase não está ativo neste ambiente")

    safe_proj = secure_filename(project)
    project_queue_dir = os.path.join(QUEUE_DIR, safe_proj)
    os.makedirs(project_queue_dir, exist_ok=True)
    
    confirmed_files = []
    for file_info in files_info:
        name = file_info.get("name")
        safe_name = secure_filename(file_info.get("safe_name", ""))
        ext = file_info.get("type", "")
        
        if not safe_name:
            continue
            
        blob_path = f"temp_queue/{safe_proj}/{safe_name}"
        filepath = os.path.join(project_queue_dir, safe_name)
        
        try:
            blob = b.blob(blob_path)
            if blob.exists():
                blob.download_to_filename(filepath)
                print(f"📥 Firebase: Download pós-upload temporário concluído para {filepath}")
                confirmed_files.append({
                    "name": name,
                    "safe_name": safe_name,
                    "type": ext
                })
        except Exception as e:
            print(f"❌ Firebase: Erro ao baixar arquivo da fila {safe_name}: {e}")
            
    return jsonify(ok=True, files=confirmed_files)


@app.route("/api/queue/extract/<project>", methods=["POST"])
def api_queue_extract(project):
    data = request.json or {}
    safe_name = secure_filename(data.get("filename", ""))
    
    if not safe_name:
        return jsonify(ok=False, error="Nome de arquivo inválido")
        
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    filepath = os.path.join(project_queue_dir, safe_name)
    
    b = get_bucket()
    if not os.path.isfile(filepath) and b:
        try:
            blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
            blob = b.blob(blob_path)
            if blob.exists():
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                blob.download_to_filename(filepath)
                print(f"📥 Firebase: Arquivo temporário restaurado do backup para extração: {blob_path}")
        except Exception as ex:
            print(f"❌ Firebase: Erro ao restaurar arquivo temporário: {ex}")
            
    if not os.path.isfile(filepath):
        return jsonify(ok=False, error="Arquivo temporário não encontrado no servidor")
        
    try:
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
            
        return jsonify(ok=True, text=raw_text)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))


@app.route("/api/config/gemini", methods=["GET"])
def api_config_gemini():
    from ai.gemini_client import load_prompt, API_KEY
    try:
        base_prompt = load_prompt()
    except Exception:
        base_prompt = ""
        
    key = os.environ.get("GEMINI_API_KEY", API_KEY)
    
    review_instructions = (
        "Você é um Revisor Editorial Sênior da Evolux Academy especializado em design instrucional e revisão ortográfica.\n"
        "Sua missão é ler o rascunho de aula em Markdown abaixo e realizar uma revisão cirúrgica e rigorosa para deixá-lo impecável.\n\n"
        "DIRETRIZES DE REVISÃO:\n"
        "1. CORREÇÃO GRAMATICAL: Corrija quaisquer erros ortográficos, concordância e digitação.\n"
        "2. NÃO UNIR CABEÇALHOS AO TEXTO: O rascunho foi gerado a partir de textos de PDFs que podem conter quebras de linha. "
        "ATENÇÃO CRÍTICA: NUNCA una uma linha que começa com cabeçalhos (#, ##, ###, ####) à linha seguinte! Os títulos devem sempre ficar em suas próprias linhas, isolados. "
        "Se o rascunho contiver cabeçalhos colados na mesma linha que o texto do parágrafo seguinte (ex: '#### Sinais Duvidosos de Conjunção Carnal São indicativos que...'), "
        "corrija obrigatoriamente inserindo uma quebra de linha dupla (uma linha em branco) de forma que o título fique isolado (ex:\n"
        "#### Sinais Duvidosos de Conjunção Carnal\n\nSão indicativos que...).\n"
        "3. UNIR FRASES TRUNCADAS: Una frases no corpo dos parágrafos normais que parecem cortadas ou palavras grudadas de forma inadequada devido a quebras de páginas (ex: se encontrar algo como 'aborto.usta e ética da lei', corrija para 'aborto. A busca justa e ética da lei').\n"
        "4. SANITIZAÇÃO DE MARCAÇÕES: Remova crases ou caracteres de código das marcações especiais do nosso parser de PDF. "
        "Exemplo: se encontrar `[BOX]` ou `[/BOX]` com crases/backticks, remova as crases e garanta que fiquem puras em linhas isoladas: [BOX] e [/BOX]. "
        "Faça o mesmo para as tags de imagem: `[IMG:nome.jpg]` deve se tornar apenas [IMG:nome.jpg] sem crases.\n"
        "5. REMOVER LEGENDAS DE IMAGEM AUTOMÁTICAS: Remova qualquer legenda de imagem, descrição ou nota textual em itálico/negrito (como *Ilustração de...* ou *Legenda...*) gerada automaticamente logo abaixo ou acima das tags [IMG:...]. As tags de imagem devem aparecer totalmente isoladas em suas próprias linhas sem qualquer texto explicativo associado.\n"
        "6. NÃO ALUCINE: Mantenha todo o conteúdo didático, técnico, exercícios e formatação de cabeçalho YAML intactos. Apenas lapide a escrita e corrija as falhas de formatação/junção.\n"
        "7. Sem emojis no corpo do texto final e respeitando estritamente a estrutura acadêmica."
    )
    
    return jsonify(
        ok=True,
        key=key,
        base_prompt=base_prompt,
        review_instructions=review_instructions
    )


@app.route("/api/queue/save/<project>", methods=["POST"])
def api_queue_save(project):
    data = request.json or {}
    safe_name = secure_filename(data.get("filename", ""))
    content = data.get("content", "")
    
    if not safe_name or not content:
        return jsonify(ok=False, error="Dados inválidos")
        
    try:
        # Salva como novo .md no projeto
        dest_filename = os.path.splitext(safe_name)[0] + ".md"
        dest_path = os.path.join(_pdir(project), dest_filename)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        # Upload do novo markdown gerado para o Firebase
        _upload_file_to_firebase(project, dest_filename, is_asset=False)
        
        # Limpar arquivo temporário local e no Firebase Storage
        project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
        filepath = os.path.join(project_queue_dir, safe_name)
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
        except Exception:
            pass
            
        b = get_bucket()
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
                    print(f"🗑️ Firebase: Backup temporário removido de {blob_path}")
            except Exception:
                pass
                
        return jsonify(ok=True, saved_as=dest_filename)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))


@app.route("/api/queue/process/<project>", methods=["POST"])
def api_queue_process(project):
    data = request.json or {}
    safe_name = secure_filename(data.get("filename", ""))
    
    if not safe_name:
        return jsonify(ok=False, error="Nome de arquivo inválido")
        
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    filepath = os.path.join(project_queue_dir, safe_name)
    
    b = get_bucket()
    
    # Se o arquivo não estiver localmente (ex: container reiniciou/trocou no Vercel),
    # tenta restaurar do backup temporário do Firebase Storage
    if not os.path.isfile(filepath):
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                blob = b.blob(blob_path)
                if blob.exists():
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    blob.download_to_filename(filepath)
                    print(f"📥 Firebase: Arquivo temporário restaurado do backup: {blob_path}")
            except Exception as ex:
                print(f"❌ Firebase: Erro ao restaurar arquivo temporário: {ex}")
                
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
            
        # 4. Limpar arquivo temporário local e backup no Firebase
        try:
            os.remove(filepath)
        except Exception:
            pass
            
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
                    print(f"🗑️ Firebase: Backup temporário removido de {blob_path}")
            except Exception:
                pass
            
        return jsonify(ok=True, saved_as=dest_filename)
        
    except Exception as e:
        traceback.print_exc()
        # Garante que removemos do Firebase mesmo em caso de erro no processamento
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
            except Exception:
                pass
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
