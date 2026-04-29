"""
PDF Engine Evolux — run.py
Orquestrador escalável: processa 1 ou N arquivos .md → gera PDFs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODOS DE USO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PASTA DE INPUT (mais simples — recomendado)
   Coloque seus .md em  inputs/
   Execute:  python run.py
   PDFs saem em  outputs/

2. ARQUIVO ÚNICO
   python run.py --md caminho/aula01.md

3. MÚLTIPLOS ARQUIVOS
   python run.py --md aula01.md aula02.md aula03.md

4. PASTA ESPECÍFICA
   python run.py --pasta /caminho/pasta/com/mds/

5. MODO INTERATIVO (digita o caminho na hora)
   python run.py --input

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPCIONAL — front-matter no .md para definir título e número:
   ---
   title: Medicina Legal
   aula: 02
   ---
   # Conteúdo começa aqui...
Se não tiver front-matter, o título vem do primeiro # Heading.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ASSETS (imagem de capa, logo):
  • Coloque cover.jpg / cover.png na mesma pasta do .md  (por aula)
  • OU coloque em  inputs/assets/cover.jpg  (compartilhado por todas)
  • Logo Evolux é usado automaticamente se não houver logo local.
"""

import os
import sys
import glob
import time

# ── Diretórios padrão ──
_BASE   = os.path.dirname(os.path.abspath(__file__))
INPUTS  = os.path.join(_BASE, "inputs")
OUTPUTS = os.path.join(_BASE, "outputs")


# ════════════════════════════════════════
# NÚCLEO
# ════════════════════════════════════════
def process_file(md_path: str, output_dir: str = OUTPUTS,
                 assets_override: str = None) -> str | None:
    """
    Processa um único .md e gera o PDF em output_dir.
    Retorna o caminho do PDF gerado ou None em caso de erro.
    """
    from engine.template import build_from_md, extract_meta

    md_path = os.path.abspath(md_path)
    stem    = os.path.splitext(os.path.basename(md_path))[0]

    # Pasta de assets: mesma do .md → inputs/assets → nenhuma
    if assets_override:
        assets = assets_override
    else:
        local_assets = os.path.join(os.path.dirname(md_path), "assets")
        shared_assets = os.path.join(INPUTS, "assets")
        if os.path.isdir(local_assets):
            assets = local_assets
        elif os.path.isdir(shared_assets):
            assets = shared_assets
        else:
            assets = os.path.dirname(md_path)  # fallback: mesmo dir do .md

    output_path = os.path.join(output_dir, f"{stem}.pdf")
    os.makedirs(output_dir, exist_ok=True)

    try:
        meta = extract_meta(md_path)
        print(f"📄 {os.path.basename(md_path)}  →  Aula {meta['aula']}: {meta['title']}")
        build_from_md(md_path, output_path, assets_dir=assets, meta=meta)
        return output_path
    except Exception as e:
        print(f"  ❌ Erro: {e}")
        return None


def process_many(md_files: list[str], output_dir: str = OUTPUTS) -> list[str]:
    """Processa uma lista de arquivos .md. Retorna lista de PDFs gerados."""
    ok, fail = [], []
    total = len(md_files)

    print(f"\n{'═'*50}")
    print(f"  Processando {total} arquivo(s)...")
    print(f"{'═'*50}")

    t0 = time.time()
    for i, md in enumerate(md_files, 1):
        print(f"\n[{i}/{total}]", end=" ")
        result = process_file(md, output_dir)
        if result:
            ok.append(result)
        else:
            fail.append(md)

    elapsed = time.time() - t0
    print(f"\n{'═'*50}")
    print(f"  ✅ {len(ok)} gerado(s)  ❌ {len(fail)} erro(s)  ⏱ {elapsed:.1f}s")
    if ok:
        print(f"  📁 PDFs em: {output_dir}")
    print(f"{'═'*50}\n")
    return ok


# ════════════════════════════════════════
# MODOS
# ════════════════════════════════════════
def mode_folder(folder: str, output_dir: str = OUTPUTS):
    """Processa todos os .md de uma pasta."""
    mds = sorted(glob.glob(os.path.join(folder, "*.md")))
    if not mds:
        print(f"⚠️  Nenhum arquivo .md encontrado em: {folder}")
        return
    process_many(mds, output_dir)


def mode_inputs():
    """Processa a pasta inputs/ padrão."""
    os.makedirs(INPUTS, exist_ok=True)
    mds = sorted(glob.glob(os.path.join(INPUTS, "*.md")))

    if not mds:
        print(f"""
  ┌─────────────────────────────────────────────┐
  │  Pasta inputs/ está vazia.                  │
  │                                             │
  │  Coloque seus arquivos .md em:              │
  │    {INPUTS:<43}│
  │                                             │
  │  Depois rode  python run.py  novamente.     │
  │                                             │
  │  Dica: coloque cover.jpg em inputs/assets/  │
  │  para usar a mesma foto em todas as capas.  │
  └─────────────────────────────────────────────┘
""")
        return

    process_many(mds)


def mode_interactive():
    """Modo interativo: usuário digita o caminho do .md."""
    print("\n  Modo interativo — PDF Engine Evolux")
    print("  Digite 'sair' para encerrar.\n")

    while True:
        raw = input("  Caminho do .md (ou pasta): ").strip().strip('"').strip("'")
        if raw.lower() in ("sair", "exit", "quit", "q"):
            break
        if not raw:
            continue

        if os.path.isdir(raw):
            mode_folder(raw)
        elif raw.endswith(".md") and os.path.isfile(raw):
            result = process_file(raw)
            if result:
                print(f"\n  Abrir: {result}\n")
        else:
            print(f"  ⚠️  Não encontrado: {raw}")


# ════════════════════════════════════════
# CLI
# ════════════════════════════════════════
def main():
    args = sys.argv[1:]

    # ── --input / --interativo ──
    if not args or args[0] in ("--input", "--interativo", "-i"):
        if not args:
            mode_inputs()   # sem argumentos → processa inputs/
        else:
            mode_interactive()
        return

    # ── --pasta <dir> ──
    if args[0] in ("--pasta", "--dir", "-p"):
        folder = args[1] if len(args) > 1 else INPUTS
        output = args[2] if len(args) > 2 else OUTPUTS
        mode_folder(folder, output)
        return

    # ── --md <arquivo> [arquivo2] ... ──
    if args[0] in ("--md", "-m"):
        files = [a for a in args[1:] if not a.startswith("-")]
        if not files:
            print("Uso: python run.py --md arquivo1.md arquivo2.md ...")
            sys.exit(1)
        output = OUTPUTS
        # --saida <dir>
        if "--saida" in args:
            idx = args.index("--saida")
            if idx + 1 < len(args): output = args[idx + 1]
        process_many([os.path.abspath(f) for f in files], output)
        return

    # ── Legado: python run.py aula03 ──
    if not args[0].startswith("-"):
        from engine.template import build
        aula   = args[0]
        md_arg = None
        if "--md" in args:
            idx = args.index("--md")
            if idx + 1 < len(args): md_arg = args[idx + 1]
        try:
            build(aula, md_file=md_arg)
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)
        return

    print(__doc__)


if __name__ == "__main__":
    main()
