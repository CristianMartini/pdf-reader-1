"""
Gemini Client — ai/gemini_client.py
Gera conteúdo educacional em markdown usando a Gemini API.
SDK: google-genai (pip install google-genai)
"""

import os
from google import genai

# Configuração via variável de ambiente (nunca hardcode a key)
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not API_KEY:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não foi definida! Cancele com Ctrl+C e configure-a no terminal.")

client = genai.Client(api_key=API_KEY)

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.md")


def load_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def generate_md(topic: str, model: str = "gemini-3-flash-preview") -> str:
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
