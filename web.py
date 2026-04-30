import os
import sys
import glob
import json
import traceback
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from run import process_file
from engine.template import extract_meta

# ── Caminhos base ──
BASE    = os.path.dirname(os.path.abspath(__file__))
INPUTS  = os.path.join(BASE, "inputs")
ASSETS  = os.path.join(INPUTS, "assets")
OUTPUTS = os.path.join(BASE, "outputs")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB

os.makedirs(INPUTS, exist_ok=True)
os.makedirs(ASSETS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/files")
def api_files():
    mds = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(INPUTS, "*.md")))]
    imgs = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(ASSETS, "*.*")))]
    pdf_paths = sorted(Path(OUTPUTS).glob("**/*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    pdfs = [str(p.relative_to(OUTPUTS)).replace('\\', '/') for p in pdf_paths]
    return jsonify(mds=mds, imgs=imgs, pdfs=pdfs)

@app.route("/api/file/<filename>")
def api_get_file(filename):
    path = os.path.join(INPUTS, secure_filename(filename))
    if not os.path.isfile(path):
        return jsonify(ok=False, error="Arquivo não encontrado")
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    meta = extract_meta(path)
    return jsonify(ok=True, content=content, meta=meta)

@app.route("/api/save", methods=["POST"])
def api_save():
    data = request.json
    filename = secure_filename(data.get("filename"))
    content = data.get("content", "")
    
    path = os.path.join(INPUTS, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return jsonify(ok=True)

@app.route("/api/upload/<type>", methods=["POST"])
def upload(type):
    files = request.files.getlist("files")
    dest_dir = INPUTS if type == "md" else ASSETS
    
    saved = 0
    for f in files:
        if f.filename:
            name = secure_filename(f.filename)
            f.save(os.path.join(dest_dir, name))
            saved += 1
            
    return jsonify(ok=True, saved=saved)

@app.route("/api/delete/<type>/<filename>", methods=["DELETE"])
def delete_file(type, filename):
    filename = secure_filename(filename)
    if type == "md": path = os.path.join(INPUTS, filename)
    elif type == "img": path = os.path.join(ASSETS, filename)
    elif type == "pdf": path = os.path.join(OUTPUTS, filename)
    else: return jsonify(ok=False)
    
    if os.path.isfile(path):
        os.remove(path)
        return jsonify(ok=True)
    return jsonify(ok=False, error="Não encontrado")

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json
    files = data.get("files", [])
    if not files: return jsonify(ok=False, error="Nenhum arquivo enviado")
    
    results = []
    try:
        for fname in files:
            md_path = os.path.join(INPUTS, secure_filename(fname))
            if os.path.isfile(md_path):
                out = process_file(md_path, OUTPUTS)
                if out: results.append(os.path.basename(out))
        return jsonify(ok=True, result=results)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error=str(e))

@app.route("/outputs/<path:filename>")
def serve_output(filename):
    safe_path = os.path.normpath(filename).replace('\\', '/')
    if safe_path.startswith('..'):
        return jsonify(ok=False, error='Caminho inválido'), 400
    return send_from_directory(OUTPUTS, safe_path)

if __name__ == "__main__":
    print("\n" + "═"*50)
    print("  ⚡ PDF Engine Evolux — Modo Editor Web")
    print("  Abra no navegador:  http://localhost:5000")
    print("═"*50 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
