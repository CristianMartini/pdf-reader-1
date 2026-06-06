"""
Gemini Client — ai/gemini_client.py
Gera conteúdo educacional em markdown usando a Gemini API.
SDK: google-genai (pip install google-genai)
"""

import os
import time
import random
import traceback
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


def generate_content_with_retry(client, model, contents, max_retries=5, initial_backoff=2):
    """
    Executa client.models.generate_content com lógica de retentativa exponencial.
    Cobre erros 503 (UNAVAILABLE), 429 (RESOURCE_EXHAUSTED/Rate Limit) e erros de rede temporários.
    """
    backoff = initial_backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            return response
        except Exception as e:
            err_msg = str(e)
            is_temporary = any(term in err_msg for term in [
                "503", "504", "429", "UNAVAILABLE", "ResourceExhausted", 
                "RESOURCE_EXHAUSTED", "ServiceUnavailable", "temporary", 
                "Please try again later", "overloaded", "high demand"
            ])
            
            # Se for a última tentativa ou o erro não for temporário, joga a exceção
            if attempt == max_retries - 1 or not is_temporary:
                print(f"❌ Gemini: Falha definitiva no generate_content na tentativa {attempt + 1}: {e}")
                raise e
            
            # Aplica backoff exponencial com jitter
            sleep_time = backoff + random.uniform(0, 1)
            print(f"⚠️ Gemini: Erro temporário ({err_msg}). Tentativa {attempt + 1}/{max_retries} falhou. Retentando em {sleep_time:.2f}s...")
            time.sleep(sleep_time)
            backoff *= 2 # Dobra o intervalo


def generate_md(topic: str, model: str = "gemini-2.5-flash") -> str:
    """
    Gera conteúdo .md educacional para um tema.
    Retorna o texto markdown gerado pelo Gemini.
    """
    base_prompt = load_prompt()
    full_prompt = f"{base_prompt}\n\nTEMA: {topic}"

    response = generate_content_with_retry(
        client=client,
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
        "títulos (#, ##, ###, ####), parágrafos separados por uma linha em branco, listas com traços, e adicione pelo menos "
        "um bloco [BOX] para fixação de conteúdo importante. Insira tags de imagem sugestivas baseadas no contexto. "
        "As tags de imagem devem usar obrigatoriamente a sintaxe `[IMG:nome_especifico.png] (Descrição detalhada em parênteses na mesma linha sugerindo a imagem/diagrama)` "
        "em sua própria linha isolada (ex: `[IMG:lesao_defesa.png] (Fotografia de lesão típica no antebraço ou diagrama anatômico)`). "
        "NUNCA gere qualquer legenda em itálico ou texto descritivo nas linhas abaixo ou acima das tags [IMG:...].\n\n"
        f"CONTEÚDO BRUTO A SER REESCRITO:\n{raw_content}"
    )

    response = generate_content_with_retry(
        client=client,
        model=model,
        contents=full_prompt,
    )
    return response.text


def review_and_polish_markdown(draft_markdown: str, model: str = "gemini-2.5-flash") -> str:
    """
    Atua como um Revisor Editorial Sênior da Evolux Academy.
    Analisa o rascunho em markdown, corrige erros gramaticais, une frases truncadas,
    garante a coesão pedagógica, sanitiza as tags de imagem e caixas [BOX] e retorna o markdown lapidado.
    """
    review_prompt = (
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
        "Faça o mesmo para as tags de imagem: `[IMG:nome.jpg]` deve se tornar apenas [IMG:nome.jpg] sem crases. "
        "Se houver uma descrição em parênteses na mesma linha da tag de imagem, mantenha-a (ex: [IMG:cadaver.png] (descrição)).\n"
        "5. LEGENDAS DE IMAGEM: A descrição/sugestão do tipo de imagem deve constar exclusivamente entre parênteses e na mesma linha da tag (ex: `[IMG:esquema.png] (Diagrama comparativo X e Y)`). Remova qualquer legenda de imagem, descrição ou nota explicativa em itálico/negrito gerada automaticamente nas linhas abaixo ou acima das tags de imagem.\n"
        "6. NÃO ALUCINE: Mantenha todo o conteúdo didático, técnico, exercícios e formatação de cabeçalho YAML intactos. Apenas lapide a escrita e corrija as falhas de formatação/junção.\n"
        "7. PROIBIÇÃO DE BLOCKQUOTES (>): Nunca use o caractere '>' no início de linhas para citações ou destaques. Se o rascunho contiver blockquotes (ex: '> texto'), remova obrigatoriamente o caractere '>' e transforme-o em texto normal ou coloque dentro de um bloco [BOX] se for muito importante.\n"
        "8. Sem emojis no corpo do texto final e respeitando estritamente a estrutura acadêmica.\n\n"
        f"RASCUNHO A SER REVISADO:\n{draft_markdown}"
    )

    response = generate_content_with_retry(
        client=client,
        model=model,
        contents=review_prompt,
    )
    return response.text
