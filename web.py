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

import sys
import io
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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

def _parse_firebase_credentials() -> dict:
    raw_cred = os.environ.get("FIREBASE_CREDENTIALS")
    if not raw_cred:
        return None
    cred_str = raw_cred.strip()
    # Remove aspas extras se presentes
    if len(cred_str) >= 2 and (
        (cred_str.startswith('"') and cred_str.endswith('"')) or
        (cred_str.startswith("'") and cred_str.endswith("'"))
    ):
        cred_str = cred_str[1:-1].strip()
        
    try:
        cred_json = json.loads(cred_str)
    except Exception as e:
        print(f"❌ Firebase: Falha ao decodificar JSON das credenciais: {e}")
        raise e
        
    if isinstance(cred_json, dict) and "private_key" in cred_json:
        pk = cred_json["private_key"]
        if isinstance(pk, str) and "\\n" in pk:
            cred_json["private_key"] = pk.replace("\\n", "\n")
            
    return cred_json


def init_firebase():
    global firebase_app, bucket
    
    # 1. Resolve credentials and project_id first
    cred = None
    project_id = None
    service_key_path = os.path.join(BASE, "serviceAccountKey.json")
    
    # Try environment variable (either from .env locally or Vercel dashboard in production)
    if os.environ.get("FIREBASE_CREDENTIALS"):
        try:
            cred_json = _parse_firebase_credentials()
            if cred_json:
                cred = credentials.Certificate(cred_json)
                project_id = cred_json.get("project_id")
                print("🔥 Firebase: Carregando chave de FIREBASE_CREDENTIALS env")
        except Exception as e:
            print(f"❌ Firebase: Erro ao ler FIREBASE_CREDENTIALS env: {e}")
    # Try local file
    elif os.path.exists(service_key_path):
        try:
            cred = credentials.Certificate(service_key_path)
            with open(service_key_path, "r", encoding="utf-8") as f:
                project_id = json.load(f).get("project_id")
            print("🔥 Firebase: Carregando chave de serviceAccountKey.json")
        except Exception as e:
            print(f"❌ Firebase: Erro ao ler serviceAccountKey.json: {e}")
            
    if not cred or not project_id:
        print("⚠️ Firebase: Nenhuma credencial ou project_id encontrado. Rodando apenas em modo local.")
        return

    bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET")
    if not bucket_name:
        bucket_name = f"{project_id}.firebasestorage.app"
    
    # 2. Initialize or retrieve the app
    try:
        if firebase_admin._apps:
            firebase_app = firebase_admin.get_app()
        else:
            firebase_app = firebase_admin.initialize_app(cred, {
                "storageBucket": bucket_name
            })
        
        # Always get the bucket with the explicit name to be safe
        bucket = storage.bucket(name=bucket_name, app=firebase_app)
        print(f"🔥 Firebase: Inicializado com bucket {bucket_name}")
    except Exception as e:
        print(f"❌ Firebase: Falha na inicialização: {e}")

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
        print(f"⚠️ Firebase: Não foi possível atualizar CORS no bucket (esperado em chaves restritas): {e}")

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
        # Check if the error is a 403 Forbidden (Permission Denied).
        # Standard Firebase keys might lack getBucket metadata permission but can still read/write blobs.
        is_forbidden = False
        if hasattr(e, "code") and e.code == 403:
            is_forbidden = True
        elif "403" in str(e):
            is_forbidden = True
            
        if is_forbidden:
            print(f"🔥 Firebase: Bucket {bucket.name} retornou 403 (Permissão restrita de metadados, mas aceita uploads). Mantendo.")
            _bucket_resolved = True
            return bucket
            
        # If it was a 404 (Not Found) or other error, and was the default bucket, try the fallback (.appspot.com)
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
                fallback_forbidden = False
                if hasattr(ex, "code") and ex.code == 403:
                    fallback_forbidden = True
                elif "403" in str(ex):
                    fallback_forbidden = True
                    
                if fallback_forbidden:
                    bucket = fallback_bucket
                    print(f"🔥 Firebase: Fallback bucket {bucket.name} retornou 403. Mantendo.")
                else:
                    # Se tudo falhar, restaura o padrão e não fica tentando em cada request
                    # (isso evita timeouts recorrentes no Vercel causados por validações repetidas)
                    bucket = storage.bucket(name=bucket.name, app=firebase_app)
                    print(f"⚠️ Firebase: Validação falhou em ambos os formatos. Mantendo padrão {bucket.name}. Erro: {ex}")
                _bucket_resolved = True
        else:
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
            
            # ATENÇÃO: Sincroniza localmente apenas markdowns, .keep e project_info.json.
            # Imagens e PDFs são armazenados na nuvem e baixados sob demanda.
            if not (rel_path.endswith(".md") or rel_path == ".keep" or rel_path == "project_info.json"):
                continue
                
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


def _upload_file_to_firebase_ex(project_name: str, filename: str, kind: str):
    """Upload with explicit kind (md, img, cover, etc.)."""
    b = get_bucket()
    if not b:
        return

    try:
        local_proj_dir = os.path.join(PROJECTS, project_name)
        if kind == "img":
            local_path = os.path.join(local_proj_dir, "assets", filename)
            blob_path = f"projects/{project_name}/assets/{filename}"
        elif kind == "cover":
            local_path = os.path.join(local_proj_dir, "covers", filename)
            blob_path = f"projects/{project_name}/covers/{filename}"
        else:
            local_path = os.path.join(local_proj_dir, filename)
            blob_path = f"projects/{project_name}/{filename}"

        if os.path.isfile(local_path):
            blob = b.blob(blob_path)
            blob.upload_from_filename(local_path)
            print(f"📤 Firebase: Upload concluído para {blob_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao fazer upload de {filename}: {e}")


def _download_file_from_firebase(project_name: str, filename: str, is_asset: bool = False) -> bool:
    b = get_bucket()
    if not b:
        return False
    try:
        local_proj_dir = os.path.join(PROJECTS, project_name)
        if is_asset:
            local_path = os.path.join(local_proj_dir, "assets", filename)
            blob_path = f"projects/{project_name}/assets/{filename}"
        else:
            local_path = os.path.join(local_proj_dir, filename)
            blob_path = f"projects/{project_name}/{filename}"
            
        blob = b.blob(blob_path)
        if blob.exists():
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"📥 Firebase: Sincronizado arquivo individual {blob_path} -> {local_path}")
            return True
    except Exception as e:
        print(f"❌ Firebase: Erro ao baixar arquivo individual {filename}: {e}")
    return False


def _download_cover_from_firebase(project_name: str, filename: str) -> bool:
    b = get_bucket()
    if not b:
        return False
    try:
        local_path = os.path.join(_cdir(project_name), filename)
        blob_path = f"projects/{project_name}/covers/{filename}"
        blob = b.blob(blob_path)
        if blob.exists():
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"📥 Firebase: Sincronizado cover {blob_path} -> {local_path}")
            return True
    except Exception as e:
        print(f"❌ Firebase: Erro ao baixar cover {filename}: {e}")
    return False


def _download_all_assets(project_name: str):
    b = get_bucket()
    if not b:
        return
    try:
        prefix = f"projects/{project_name}/assets/"
        blobs = b.list_blobs(prefix=prefix)
        local_adir = _adir(project_name)
        for blob in blobs:
            if blob.name.endswith('/'):
                continue
            rel_path = os.path.relpath(blob.name, f"projects/{project_name}/assets")
            local_path = os.path.join(local_adir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"📥 Firebase PDF Gen: Baixado asset {blob.name} -> {local_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao baixar todos os assets para PDF gen: {e}")

    # Também baixa capas da pasta covers/
    try:
        prefix_c = f"projects/{project_name}/covers/"
        blobs_c = b.list_blobs(prefix=prefix_c)
        local_cdir = _cdir(project_name)
        for blob in blobs_c:
            if blob.name.endswith('/'):
                continue
            rel_path = os.path.relpath(blob.name, f"projects/{project_name}/covers")
            local_path = os.path.join(local_cdir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"📥 Firebase PDF Gen: Baixado cover {blob.name} -> {local_path}")
    except Exception as e:
        print(f"❌ Firebase: Erro ao baixar covers para PDF gen: {e}")


def _delete_file_from_firebase(project_name: str, filename: str, kind: str):
    b = get_bucket()
    if not b:
        return
        
    try:
        if kind == "img":
            blob_path = f"projects/{project_name}/assets/{filename}"
        elif kind == "cover":
            blob_path = f"projects/{project_name}/covers/{filename}"
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

def _cdir(project: str) -> str:
    return os.path.join(_pdir(project), "covers")


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
    
    b = get_bucket()
    for name in sorted(project_names):
        if b:
            counts = _firebase_count_files(name)
            mds = counts["mds"]
            pdfs = counts["pdfs"]
        else:
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
    os.makedirs(_cdir(safe), exist_ok=True)
    
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
        import time
        import stat
        
        # Renomeia a pasta para um diretório oculto antes de apagar para sumir da listagem imediatamente,
        # mesmo se a exclusão física falhar devido a bloqueios do Windows (arquivos abertos)
        deleted_name = f".deleted_{secure_filename(project)}_{int(time.time())}"
        dp = os.path.join(PROJECTS, deleted_name)
        try:
            os.rename(pd, dp)
            target_dir = dp
        except Exception as e:
            print(f"⚠️ Windows: Não foi possível renomear a pasta do projeto: {e}")
            target_dir = pd
            
        try:
            # Tenta remover recursivamente com manipulador de permissão somente-leitura
            def remove_readonly(func, path, excinfo):
                os.chmod(path, stat.S_IWRITE)
                func(path)
            shutil.rmtree(target_dir, onerror=remove_readonly)
        except Exception as e:
            print(f"⚠️ Erro ao remover pasta do projeto local: {e}")
            
    # Exclui todos os arquivos do projeto no Firebase (mesmo que o diretório local não exista)
    _delete_project_from_firebase(project)
    return jsonify(ok=True)


# ════════════════════════════════════════
# ARQUIVOS DO PROJETO
# ════════════════════════════════════════
@app.route("/api/files/<project>")
def api_files(project):
    force = request.args.get("force", "").lower() == "true"
    # Sincroniza apenas markdowns do Firebase
    _sync_project_from_firebase(project, force=force)
    
    b = get_bucket()
    mds = []
    imgs = []
    pdfs = []
    covers = []
    
    if b:
        try:
            prefix = f"projects/{project}/"
            blobs = list(b.list_blobs(prefix=prefix))
            # Ordena blobs pelo tempo de modificação (updated) decrescente
            blobs_sorted = sorted(blobs, key=lambda x: x.updated if x.updated else 0, reverse=True)
            
            for blob in blobs_sorted:
                if blob.name.endswith('/'):
                    continue
                rel_path = os.path.relpath(blob.name, f"projects/{project}")
                # Normaliza separadores de caminho para barras normais (essencial no Windows)
                rel_path = rel_path.replace('\\', '/')
                if rel_path == ".keep":
                    continue
                    
                if rel_path.startswith("covers/"):
                    cover_name = os.path.basename(rel_path)
                    if cover_name and cover_name not in covers:
                        covers.append(cover_name)
                elif rel_path.startswith("assets/"):
                    img_name = os.path.basename(rel_path)
                    if img_name and img_name not in imgs:
                        imgs.append(img_name)
                elif rel_path.endswith(".pdf"):
                    pdf_name = os.path.basename(rel_path)
                    if pdf_name and pdf_name not in pdfs:
                        pdfs.append(pdf_name)
                elif rel_path.endswith(".md"):
                    md_name = os.path.basename(rel_path)
                    if md_name and md_name not in mds:
                        mds.append(md_name)
            
            # Markdowns são exibidos ordenados alfabeticamente
            mds.sort()
        except Exception as e:
            print(f"❌ Firebase: Erro ao listar arquivos de {project}: {e}")
            
    # Fallback para listagem local caso o Firebase falhe
    if not mds and not imgs and not pdfs and not covers:
        pd = _pdir(project)
        ad = _adir(project)
        cd = _cdir(project)
        mds  = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(pd, "*.md")))]
        imgs = [os.path.basename(p) for p in sorted(
            glob.glob(os.path.join(ad, "*.*")), key=os.path.getmtime, reverse=True
        )]
        pdfs = [os.path.basename(p) for p in sorted(
            glob.glob(os.path.join(pd, "*.pdf")), key=os.path.getmtime, reverse=True
        )]
        if os.path.isdir(cd):
            covers = [os.path.basename(p) for p in sorted(
                glob.glob(os.path.join(cd, "*.*")), key=os.path.getmtime, reverse=True
            )]
        
    return jsonify(mds=mds, imgs=imgs, pdfs=pdfs, covers=covers)



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
    if kind == "md":
        dest_dir = _pdir(project)
    elif kind == "cover":
        dest_dir = _cdir(project)
    else:
        dest_dir = _adir(project)
    os.makedirs(dest_dir, exist_ok=True)
    saved = 0
    for f in files:
        if f.filename:
            safe_name = secure_filename(f.filename)
            local_path = os.path.join(dest_dir, safe_name)
            f.save(local_path)
            # Upload para o Firebase
            _upload_file_to_firebase_ex(project, safe_name, kind)
            saved += 1
            
            # Remove o arquivo local se for uma imagem ou PDF para economizar espaço
            if kind != "md":
                try:
                    os.remove(local_path)
                except Exception:
                    pass
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
    elif kind == "cover":
        blob_path = f"projects/{secure_filename(project)}/covers/{safe_name}"
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
    elif kind == "cover":
        blob_path = f"projects/{safe_proj}/covers/{filename}"
        local_path = os.path.join(_cdir(safe_proj), filename)
    else:
        return jsonify(ok=False, error="Tipo inválido")

    try:
        blob = b.blob(blob_path)
        if blob.exists():
            if kind == "md":
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                blob.download_to_filename(local_path)
                print(f"📥 Firebase: Download pós-upload concluído para {local_path}")
            else:
                # Evita salvar arquivos grandes de mídia localmente no container serverless
                print(f"✅ Firebase: Confirmado upload de asset remoto {blob_path}")
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
    elif kind == "cover":
        path = os.path.join(_cdir(project), filename)
    elif kind == "pdf":
        path = os.path.join(_pdir(project), filename)
    else:
        return jsonify(ok=False, error="Tipo inválido")
    if os.path.isfile(path):
        os.remove(path)
    # Excluir do Firebase (mesmo que não exista localmente)
    _delete_file_from_firebase(project, filename, kind)
    return jsonify(ok=True)


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
        # Sincroniza apenas markdowns do Firebase antes da geração
        _sync_project_from_firebase(project, force=True)
        # Pré-baixa todas as imagens (assets) necessárias para compilação local
        _download_all_assets(project)

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
                
                # Remove o PDF local imediatamente após o upload para economizar espaço
                try:
                    os.remove(output_path)
                except Exception:
                    pass
        return jsonify(ok=True, result=results)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))
    finally:
        # Garante a limpeza de toda a pasta de assets locais temporários do container serverless
        try:
            if os.path.isdir(ad):
                shutil.rmtree(ad)
                print(f"🗑️ Local: Limpo diretório de assets temporários pós-compilação: {ad}")
        except Exception as ex:
            print(f"⚠️ Erro ao limpar assets temporários: {ex}")
        # Limpa também a pasta de covers temporários
        cd = _cdir(project)
        try:
            if os.path.isdir(cd):
                shutil.rmtree(cd)
                print(f"🗑️ Local: Limpo diretório de covers temporários pós-compilação: {cd}")
        except Exception as ex:
            print(f"⚠️ Erro ao limpar covers temporários: {ex}")


# ════════════════════════════════════════
# SERVIR PDFs E INSTRUÇÕES
# ════════════════════════════════════════
@app.route("/projects/<project>/pdf/<path:filename>")
def serve_pdf(project, filename):
    filepath = os.path.join(_pdir(project), filename)
    if not os.path.isfile(filepath):
        _download_file_from_firebase(project, filename, is_asset=False)
    return send_from_directory(_pdir(project), filename)

@app.route("/projects/<project>/assets/<path:filename>")
def serve_asset(project, filename):
    filepath = os.path.join(_adir(project), filename)
    if not os.path.isfile(filepath):
        _download_file_from_firebase(project, filename, is_asset=True)
    return send_from_directory(_adir(project), filename)

@app.route("/projects/<project>/covers/<path:filename>")
def serve_cover(project, filename):
    filepath = os.path.join(_cdir(project), filename)
    if not os.path.isfile(filepath):
        _download_cover_from_firebase(project, filename)
    return send_from_directory(_cdir(project), filename)

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
    import re
    from pypdf import PdfReader
    
    print(f"📄 Extraindo texto de PDF de forma otimizada com coordenadas e repetições: {filepath}")
    reader = PdfReader(filepath)
    
    pages_lines = []
    header_footer_candidates = {}
    
    for page in reader.pages:
        mb = page.mediabox
        height = mb.top - mb.bottom
        
        page_texts = []
        
        def visitor(text, cm, tm, font_dict, font_size):
            y_abs = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            pct_y = y_abs / height if height > 0 else 0.5
            
            # Margem superior (8% do topo): pct_y > 0.92
            # Margem inferior (8% da base): pct_y < 0.08
            is_margin = pct_y > 0.92 or pct_y < 0.08
            
            if not is_margin and text.strip():
                page_texts.append(text)
                
        page.extract_text(visitor_text=visitor)
        
        if page_texts:
            t = "".join(page_texts)
            lines = [line.strip() for line in t.splitlines()]
            pages_lines.append(lines)
            
            # Coleta candidatos a cabeçalho/rodapé do corpo restante (primeiras 2 e últimas 2 linhas)
            candidates = []
            if len(lines) >= 1:
                candidates.append(lines[0])
            if len(lines) >= 2:
                candidates.append(lines[1])
            if len(lines) >= 2:
                candidates.append(lines[-1])
            if len(lines) >= 3:
                candidates.append(lines[-2])
                
            for c in set(candidates):
                if c:
                    header_footer_candidates[c] = header_footer_candidates.get(c, 0) + 1
        else:
            pages_lines.append([])
            
    # Se a mesma linha se repete em 3 ou mais páginas na borda, é considerada cabeçalho/rodapé
    header_footers = {line for line, count in header_footer_candidates.items() if count >= 3}
    
    cleaned_text_parts = []
    for lines in pages_lines:
        cleaned_lines = []
        for line in lines:
            if line in header_footers:
                continue
                
            # Heurística para pular numerações de página (Ex: Página 1, Pag 2, 3 de 10, numerais sozinhos)
            lower_line = line.lower()
            if re.match(r'^p[áa]g\s*\.?\s*\d+$|^p[áa]gina\s*\d+$|^\d+$|^\d+\s*/\s*\d+$|^\d+\s*de\s*\d+$', lower_line):
                continue
                
            cleaned_lines.append(line)
        if cleaned_lines:
            cleaned_text_parts.append("\n".join(cleaned_lines))
            
    full_text = "\n\n".join(cleaned_text_parts)
    # Reduz quebras de linha consecutivas excessivas para economizar tokens
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    return full_text


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
            
            ext = os.path.splitext(safe_name)[1].lower()
            
            if ext == ".pdf":
                # Extrai texto imediatamente no upload
                try:
                    raw_text = _extract_text_from_pdf(filepath)
                    txt_filepath = filepath + ".txt"
                    with open(txt_filepath, "w", encoding="utf-8") as txt_f:
                        txt_f.write(raw_text)
                    
                    # Remove o PDF binário original localmente de imediato
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                        
                    # Envia apenas o backup temporário de texto (.txt) para o Firebase
                    if b:
                        try:
                            blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}.txt"
                            blob = b.blob(blob_path)
                            blob.upload_from_filename(txt_filepath)
                            print(f"📤 Firebase: Backup temporário de texto concluído para {blob_path}")
                        except Exception as ex:
                            print(f"⚠️ Firebase: Falha no backup temporário: {ex}")
                except Exception as ex:
                    print(f"❌ Erro na extração imediata do PDF: {ex}")
            else:
                # Arquivos MD ou TXT normais
                if b:
                    try:
                        blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                        blob = b.blob(blob_path)
                        blob.upload_from_filename(filepath)
                        print(f"📤 Firebase: Backup temporário concluído para {blob_path}")
                    except Exception as ex:
                        print(f"⚠️ Firebase: Falha no backup temporário: {ex}")
            
            uploaded_files.append({
                "name": f.filename,
                "safe_name": safe_name,
                "type": ext.replace(".", "")
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
            
        is_pdf = safe_name.lower().endswith(".pdf") or ext.lower() == "pdf"
        
        if is_pdf:
            # O navegador fez upload direto do PDF binário para f"temp_queue/{safe_proj}/{safe_name}"
            pdf_blob_path = f"temp_queue/{safe_proj}/{safe_name}"
            pdf_filepath = os.path.join(project_queue_dir, safe_name)
            txt_filepath = pdf_filepath + ".txt"
            
            try:
                pdf_blob = b.blob(pdf_blob_path)
                if pdf_blob.exists():
                    # 1. Download do PDF binário temporário do Firebase
                    pdf_blob.download_to_filename(pdf_filepath)
                    
                    # 2. Extração de texto imediata localmente
                    raw_text = _extract_text_from_pdf(pdf_filepath)
                    with open(txt_filepath, "w", encoding="utf-8") as txt_f:
                        txt_f.write(raw_text)
                    
                    # 3. Envia o backup de texto para o Firebase
                    txt_blob_path = pdf_blob_path + ".txt"
                    txt_blob = b.blob(txt_blob_path)
                    txt_blob.upload_from_filename(txt_filepath)
                    print(f"📤 Firebase: Backup temporário de texto concluído para {txt_blob_path}")
                    
                    # 4. Deleta o PDF binário no Firebase
                    try:
                        pdf_blob.delete()
                        print(f"🗑️ Firebase: PDF binário deletado do storage: {pdf_blob_path}")
                    except Exception as ex:
                        print(f"⚠️ Firebase: Falha ao deletar PDF binário do storage: {ex}")
                        
                    # 5. Deleta o PDF binário localmente
                    try:
                        os.remove(pdf_filepath)
                    except Exception:
                        pass
                        
                    confirmed_files.append({
                        "name": name,
                        "safe_name": safe_name,
                        "type": ext
                    })
            except Exception as e:
                print(f"❌ Firebase: Erro ao confirmar e converter PDF {safe_name}: {e}")
        else:
            # Arquivos comuns (.md, .txt)
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
        
    ext = os.path.splitext(safe_name)[1].lower()
    is_pdf = ext == ".pdf"
    
    project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    filepath = os.path.join(project_queue_dir, safe_name)
    if is_pdf:
        filepath += ".txt"
        
    b = get_bucket()
    if not os.path.isfile(filepath) and b:
        try:
            blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
            if is_pdf:
                blob_path += ".txt"
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
        if is_pdf or ext in (".md", ".txt"):
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
            if is_pdf and not raw_text.strip():
                return jsonify(ok=False, error="O PDF parece estar vazio ou é uma imagem escaneada sem texto.")
        else:
            return jsonify(ok=False, error=f"Extensão de arquivo não suportada: {ext}")
            
        return jsonify(ok=True, text=raw_text)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))



@app.route("/api/config/gemini", methods=["GET"])
def api_config_gemini():
    from ai.gemini_client import load_prompt, API_KEY, API_KEYS
    try:
        base_prompt = load_prompt()
    except Exception:
        base_prompt = ""
        
    key = os.environ.get("GEMINI_API_KEY", API_KEY)
    
    review_instructions = (
        "Você é um Revisor Editorial Sênior da Evolux Academy especializado em design instrucional e revisão ortográfica.\n"
        "Sua missão é ler o rascunho de aula em Markdown abaixo e realizar uma revisão cirúrgica e rigorosa para deixá-lo impecável.\n\n"
        "REGRA ABSOLUTA DE SAÍDA:\n"
        "- Sua resposta deve conter EXCLUSIVAMENTE o texto Markdown revisado, começando diretamente com o bloco YAML (---) do cabeçalho.\n"
        "- NUNCA inclua preâmbulos, explicações, comentários sobre a revisão, ou qualquer texto introdutório antes do conteúdo.\n"
        "- NUNCA escreva frases como 'Como Revisor...', 'Realizei uma revisão...', 'Segue o texto revisado' etc.\n"
        "- A primeira linha da sua resposta DEVE ser exatamente '---' (o início do cabeçalho YAML).\n"
        "- Se o rascunho contiver blocos de código Markdown (```markdown ... ```), remova esses delimitadores e retorne apenas o conteúdo interno.\n\n"
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
        "Faça o mesmo para as tags de imagem: `[IMG:nome.jpg]` deve se tornar apenas [IMG:nome.jpg] sem crases. "
        "Se houver uma descrição em parênteses na mesma linha da tag de imagem, mantenha-a (ex: [IMG:cadaver.png] (descrição)).\n"
        "5. LEGENDAS DE IMAGEM: A descrição/sugestão do tipo de imagem deve constar exclusivamente entre parênteses e na mesma linha da tag (ex: `[IMG:esquema.png] (Diagrama comparativo X e Y)`). Remova qualquer legenda de imagem, descrição ou nota explicativa em itálico/negrito gerada automaticamente nas linhas abaixo ou acima das tags de imagem.\n"
        "6. NÃO ALUCINE: Mantenha todo o conteúdo didático, técnico, exercícios e formatação de cabeçalho YAML intactos. Apenas lapide a escrita e corrija as falhas de formatação/junção.\n"
        "7. PROIBIÇÃO DE BLOCKQUOTES (>): Nunca use o caractere '>' no início de linhas para citações ou destaques. Se o rascunho contiver blockquotes (ex: '> texto'), remova obrigatoriamente o caractere '>' e transforme-o em texto normal ou coloque dentro de um bloco [BOX] se for muito importante.\n"
        "8. Sem emojis no corpo do texto final e respeitando estritamente a estrutura acadêmica."
    )
    
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
    return jsonify(
        ok=True,
        key=key,
        keys=API_KEYS,
        model=model,
        base_prompt=base_prompt,
        review_instructions=review_instructions
    )


@app.route("/api/debug/firebase", methods=["GET"])
def api_debug_firebase():
    info = {
        "is_vercel": is_vercel(),
        "firebase_initialized": firebase_admin._apps is not None and len(firebase_admin._apps) > 0,
        "env_firebase_credentials_present": "FIREBASE_CREDENTIALS" in os.environ,
        "env_firebase_credentials_length": len(os.environ.get("FIREBASE_CREDENTIALS", "")),
        "local_service_account_exists": os.path.exists(os.path.join(BASE, "serviceAccountKey.json")),
        "gemini_api_key_present": "GEMINI_API_KEY" in os.environ or os.environ.get("GEMINI_API_KEY") is not None,
    }
    
    cred_error = None
    parsed_proj_id = None
    if info["env_firebase_credentials_present"]:
        try:
            cred_json = _parse_firebase_credentials()
            if cred_json:
                parsed_proj_id = cred_json.get("project_id")
                info["parsed_project_id"] = parsed_proj_id
                info["parsed_keys"] = list(cred_json.keys())
        except Exception as e:
            cred_error = f"JSON load error: {str(e)}"
            info["parse_error"] = cred_error
            
    b = get_bucket()
    if b:
        info["bucket_name"] = b.name
        info["bucket_resolved"] = _bucket_resolved
        try:
            from datetime import timedelta
            blob = b.blob("test_diagnostic.txt")
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=5),
                method="PUT",
                content_type="text/plain"
            )
            info["signed_url_generation_ok"] = True
        except Exception as e:
            info["signed_url_generation_ok"] = False
            info["signed_url_error"] = str(e)
    else:
        info["bucket_name"] = None
        info["bucket_resolved"] = False
        
    return jsonify(info)


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
        is_pdf = safe_name.lower().endswith(".pdf")
        filepath = os.path.join(project_queue_dir, safe_name)
        if is_pdf:
            filepath += ".txt"
            
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
        except Exception:
            pass
            
        b = get_bucket()
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                if is_pdf:
                    blob_path += ".txt"
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


@app.route("/api/queue/delete/<project>", methods=["POST"])
def api_queue_delete(project):
    data = request.json or {}
    safe_name = secure_filename(data.get("filename", ""))
    
    if not safe_name:
        return jsonify(ok=False, error="Nome de arquivo inválido")
        
    try:
        # 1. Limpar arquivo temporário local
        project_queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
        is_pdf = safe_name.lower().endswith(".pdf")
        filepath = os.path.join(project_queue_dir, safe_name)
        if is_pdf:
            filepath += ".txt"
            
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
        except Exception:
            pass
            
        # 2. Limpar backups no Firebase Storage
        b = get_bucket()
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                if is_pdf:
                    blob_path += ".txt"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
                    print(f"🗑️ Firebase: Backup temporário deletado: {blob_path}")
            except Exception as ex:
                print(f"⚠️ Firebase: Erro ao deletar backups: {ex}")
                
        return jsonify(ok=True)
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
    ext = os.path.splitext(safe_name)[1].lower()
    is_pdf = ext == ".pdf"
    
    filepath = os.path.join(project_queue_dir, safe_name)
    if is_pdf:
        filepath += ".txt"
        
    b = get_bucket()
    
    # Se o arquivo não estiver localmente (ex: container reiniciou/trocou no Vercel),
    # tenta restaurar do backup temporário do Firebase Storage
    if not os.path.isfile(filepath):
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                if is_pdf:
                    blob_path += ".txt"
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
        # 1. Envio para a IA Gemini (Geração + Revisão unificada e upload nativo)
        from ai.gemini_client import process_content_to_style
        
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()
            
        materia = _get_project_materia(project)
        rewritten_markdown = process_content_to_style(raw_text, is_pdf=False, filename=safe_name, materia=materia)
        rewritten_markdown = override_materia_in_markdown(rewritten_markdown, materia)
        
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
                if is_pdf:
                    blob_path += ".txt"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
                    print(f"🗑️ Firebase: Backup temporário removido de {blob_path}")
            except Exception:
                pass
            
        return jsonify(ok=True, saved_as=dest_filename)
        
    except Exception as e:
        traceback.print_exc()
        # Garante que removemos os backups do Firebase mesmo em caso de erro no processamento
        if b:
            try:
                blob_path = f"temp_queue/{secure_filename(project)}/{safe_name}"
                if is_pdf:
                    blob_path += ".txt"
                blob = b.blob(blob_path)
                if blob.exists():
                    blob.delete()
            except Exception:
                pass
        return jsonify(ok=False, error=str(e))



@app.route("/api/projects/<project>/download-mds")
def api_download_project_mds(project):
    import io
    import zipfile
    from flask import send_file

    safe_proj = secure_filename(project)
    _sync_project_from_firebase(safe_proj)
    
    pd = _pdir(safe_proj)
    md_files = glob.glob(os.path.join(pd, "*.md"))
    
    if not md_files:
        return jsonify(ok=False, error="Nenhum arquivo Markdown encontrado neste projeto")
        
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in md_files:
            basename = os.path.basename(filepath)
            zipf.write(filepath, basename)
            
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_proj}_markdowns.zip"
    )


@app.route("/api/projects/<project>/download-pdfs")
def api_download_project_pdfs(project):
    import io
    import zipfile
    from flask import send_file

    safe_proj = secure_filename(project)
    
    b = get_bucket()
    if not b:
        return jsonify(ok=False, error="Firebase inativo ou não configurado")
        
    prefix = f"projects/{safe_proj}/"
    blobs = b.list_blobs(prefix=prefix)
    
    memory_file = io.BytesIO()
    has_files = False
    
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for blob in blobs:
            if blob.name.endswith(".pdf"):
                pdf_data = blob.download_as_bytes()
                basename = os.path.basename(blob.name)
                zip_path = f"{project}/{basename}"
                zipf.writestr(zip_path, pdf_data)
                has_files = True
                
    if not has_files:
        return jsonify(ok=False, error="Nenhum PDF encontrado neste projeto")
        
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_proj}_pdfs.zip"
    )


# ════════════════════════════════════════
# PADRONIZAÇÃO DE MATÉRIA
# ════════════════════════════════════════
def _project_info_path(project):
    return os.path.join(_pdir(project), "project_info.json")

def _get_project_materia(project):
    # Força a sincronização antes de ler a matéria (importante para ambientes como Vercel)
    _sync_project_from_firebase(project)
    
    info_path = _project_info_path(project)
    if os.path.isfile(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                m = data.get("materia", "").strip()
                if m:
                    return m
        except Exception:
            pass
            
    # Fallback 1: Verifica nos markdowns existentes
    pd = _pdir(project)
    md_files = glob.glob(os.path.join(pd, "*.md"))
    md_files.sort(key=os.path.getmtime, reverse=True)
    
    from engine.template import extract_meta
    for md_path in md_files:
        try:
            meta = extract_meta(md_path)
            m = meta.get("materia", "").strip()
            if m and m.lower() != "disciplina":
                _save_project_info(project, {"materia": m})
                return m
        except Exception:
            pass
            
    # Fallback 2: Adivinha a partir do nome do projeto
    guessed = project.replace("_", " ").replace("-", " ").strip()
    guessed = " ".join(word.capitalize() for word in guessed.split())
    _save_project_info(project, {"materia": guessed})
    return guessed

def _save_project_info(project, data):
    info_path = _project_info_path(project)
    existing = {}
    if os.path.isfile(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(data)
    try:
        os.makedirs(os.path.dirname(info_path), exist_ok=True)
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        # Upload do project_info.json atualizado para o Firebase
        _upload_file_to_firebase(project, "project_info.json", is_asset=False)
    except Exception as e:
        print(f"Erro ao salvar project_info.json: {e}")

def _detect_project_materia_backend(project):
    # 1. Busca primeiro nos MDs existentes
    pd = _pdir(project)
    md_files = glob.glob(os.path.join(pd, "*.md"))
    md_files.sort(key=os.path.getmtime, reverse=True)
    from engine.template import extract_meta
    for md_path in md_files:
        try:
            meta = extract_meta(md_path)
            m = meta.get("materia", "").strip()
            if m and m.lower() != "disciplina":
                return m
        except Exception:
            pass

    # 2. Busca amostra de texto dos PDFs na fila temporária ou no diretório do projeto
    queue_dir = os.path.join(QUEUE_DIR, secure_filename(project))
    txt_files = glob.glob(os.path.join(queue_dir, "*.txt"))
    txt_files += glob.glob(os.path.join(pd, "*.txt"))
    
    raw_text_sample = ""
    for txt_path in txt_files:
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                sample = f.read(5000)
                if sample.strip():
                    raw_text_sample = sample
                    break
        except Exception:
            pass
            
    # 3. Usa IA Gemini para classificar com base na amostra de texto do PDF
    if raw_text_sample:
        try:
            from ai.gemini_client import get_client, generate_content_with_retry
            client = get_client()
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            prompt = (
                "Você é um classificador acadêmico de elite. Por favor, leia a amostra de texto abaixo extraída de um material didático "
                "e identifique qual é a disciplina, matéria ou assunto principal do curso/aula (ex: Balística, Criminologia, Direito Penal, "
                "Medicina Legal, Direito Constitucional, etc.).\n"
                "REGRA ABSOLUTA: Retorne APENAS o nome da disciplina com as primeiras letras maiúsculas, em no máximo 3 ou 4 palavras, sem preâmbulos, explicações ou comentários.\n\n"
                f"AMOSTRA DE TEXTO:\n{raw_text_sample}"
            )
            response = generate_content_with_retry(
                client=client,
                model=model,
                contents=prompt
            )
            detected = response.text.strip().replace("\n", " ").replace("*", "").replace('"', '').replace("'", "")
            if detected and len(detected) < 60:
                return detected
        except Exception as e:
            print(f"Erro ao usar Gemini para detecção de matéria: {e}")
            
    # 4. Fallback: Adivinha a partir do nome do projeto
    guessed = project.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() for word in guessed.split())

def override_materia_in_markdown(markdown_content: str, materia: str) -> str:
    import re
    import unicodedata
    if not materia:
        return markdown_content
        
    fm_pattern = r'^(\s*---\s*\n)(.*?)(\n---\s*\n)'
    fm_match = re.search(fm_pattern, markdown_content, re.DOTALL | re.MULTILINE)
    
    if fm_match:
        prefix = fm_match.group(1)
        body = fm_match.group(2)
        suffix = fm_match.group(3)
        
        lines = body.splitlines()
        materia_updated = False
        new_lines = []
        
        for line in lines:
            if ':' in line:
                key, sep, val = line.partition(':')
                norm_key = key.strip().lower()
                norm_key = ''.join(c for c in unicodedata.normalize('NFD', norm_key) if unicodedata.category(c) != 'Mn')
                if norm_key == 'materia':
                    new_lines.append(f"{key.rstrip()}:{sep} {materia}")
                    materia_updated = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        if not materia_updated:
            new_lines.append(f"materia: {materia}")
            
        new_body = "\n".join(new_lines)
        return markdown_content[:fm_match.start()] + prefix + new_body + suffix + markdown_content[fm_match.end():]
    else:
        title = "Aula"
        title_match = re.search(r'^#\s+(.+)', markdown_content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            
        fm = f"---\ntitle: {title}\naula: 01\nmateria: {materia}\n---\n\n"
        return fm + markdown_content

@app.route("/api/projects/<project>/materia", methods=["GET"])
def api_get_project_materia(project):
    try:
        materia = _get_project_materia(project)
        return jsonify(ok=True, materia=materia)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/api/projects/<project>/materia", methods=["POST"])
def api_save_project_materia(project):
    data = request.json or {}
    materia = data.get("materia", "").strip()
    if not materia:
        return jsonify(ok=False, error="Nome de matéria inválido")
    try:
        _save_project_info(project, {"materia": materia})
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/api/projects/<project>/materia/detect", methods=["POST"])
def api_detect_project_materia(project):
    try:
        detected = _detect_project_materia_backend(project)
        _save_project_info(project, {"materia": detected})
        return jsonify(ok=True, materia=detected)
    except Exception as e:
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
