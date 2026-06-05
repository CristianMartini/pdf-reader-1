"""
Gemini Client — ai/gemini_client.py
Gera conteúdo educacional em markdown usando a Gemini API.
SDK: google-genai (pip install google-genai)
"""

import os
from google import genai

# Configuração via variável de ambiente (nunca hardcode a key)
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Se não estiver no ambiente, tenta ler de um arquivo .env local (seguro e ignorado no Git)
if not API_KEY:
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception as e:
            print(f"⚠️ Erro ao ler arquivo .env: {e}")

if not API_KEY:
    raise ValueError("A chave GEMINI_API_KEY não foi encontrada! Crie um arquivo chamado '.env' na raiz do projeto e insira: GEMINI_API_KEY=sua_chave_aqui")

client = genai.Client(api_key=API_KEY)

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.md")


def load_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def generate_md(topic: str, model: str = "gemini-2.5-flash") -> str:
    """
    Gera conteúdo .md educacional para um tema.
    Retorna o texto markdown gerado pelo Gemini.
    """
    base_prompt = load_prompt()
    full_prompt = f"{base_prompt}\n\nTEMA: {topic}"

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
    )
    return response.text


def rewrite_content_to_style(raw_content: str, model: str = "gemini-2.5-flash") -> str:
    """
    Reescreve um conteúdo bruto (.md ou texto extraído de PDF) adaptando-o
    às diretrizes pedagógicas e técnicas descritas em prompt.md.
    """
    base_prompt = load_prompt()
    full_prompt = (
        f"{base_prompt}\n\n"
        "INSTRUÇÃO ADICIONAL: Reescreva e adapte o conteúdo bruto fornecido abaixo ao padrão especificado acima. "
        "Preserve o conteúdo didático e técnico, mas estruture com cabeçalho YAML apropriado (titulo, aula e materia), "
        "títulos (#, ##, ###), parágrafos separados por uma linha em branco, listas com traços, e adicione pelo menos "
        "um bloco [BOX] para fixação de conteúdo importante. Insira tags [IMG:nome_imagem.jpg] caso faça sentido pedagógico "
        "no texto, para que o usuário possa inserir imagens depois.\n\n"
        f"CONTEÚDO BRUTO A SER REESCRITO:\n{raw_content}"
    )

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
    )
    return response.text

