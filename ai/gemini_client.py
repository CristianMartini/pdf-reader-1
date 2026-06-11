"""
Gemini Client — ai/gemini_client.py
Gera conteúdo educacional em markdown usando a Gemini API.
SDK: google-genai (pip install google-genai)
"""

import os
import re
import time
import random
import traceback
from google import genai
from google.genai import types

# Configuração via variáveis de ambiente e arquivo .env (múltiplas chaves suportadas)
API_KEYS = []

def _add_key(k: str):
    if k and k.strip() and k not in API_KEYS:
        clean_k = k.strip()
        # Ignora placeholders genéricos, chaves padrão ou não configuradas
        is_placeholder = (
            clean_k.startswith("INSIRA_") or
            "chave_aqui" in clean_k.lower() or
            "chave_api" in clean_k.lower() or
            clean_k == "sua_chave_aqui" or
            clean_k == "INSIRA_SEGUNDA_CHAVE_AQUI"
        )
        if not is_placeholder:
            API_KEYS.append(clean_k)

# 1. Tenta carregar do ambiente
_add_key(os.environ.get("GEMINI_API_KEY", ""))
_add_key(os.environ.get("GEMINI_API_KEY_1", ""))
_add_key(os.environ.get("GEMINI_API_KEY_2", ""))
for i in range(3, 10):
    _add_key(os.environ.get(f"GEMINI_API_KEY_{i}", ""))

# 2. Tenta ler do .env local
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str or line_str.startswith("#"):
                    continue
                if "=" in line_str:
                    name, val = line_str.split("=", 1)
                    name = name.strip()
                    val = val.strip().strip('"').strip("'")
                    if name in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2"] or name.startswith("GEMINI_API_KEY_"):
                        _add_key(val)
    except Exception as e:
        print(f"⚠️ Erro ao ler arquivo .env: {e}")

if not API_KEYS:
    raise ValueError("A chave GEMINI_API_KEY não foi encontrada! Crie um arquivo chamado '.env' na raiz do projeto e insira: GEMINI_API_KEY=sua_chave_aqui")

# Define variáveis para compatibilidade de importação
API_KEY = API_KEYS[0]
client = genai.Client(api_key=API_KEY)

# Lista de todos os clientes Gemini disponíveis para rotação
clients = [genai.Client(api_key=k) for k in API_KEYS]

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.md")


def replace_special_symbols(text: str) -> str:
    sub_map = {
        '₀': '<sub>0</sub>', '₁': '<sub>1</sub>', '₂': '<sub>2</sub>', '₃': '<sub>3</sub>',
        '₄': '<sub>4</sub>', '₅': '<sub>5</sub>', '₆': '<sub>6</sub>', '₇': '<sub>7</sub>',
        '₈': '<sub>8</sub>', '₉': '<sub>9</sub>'
    }
    sup_map = {
        '⁰': '<sup>0</sup>', '¹': '<sup>1</sup>', '²': '<sup>2</sup>', '³': '<sup>3</sup>',
        '⁴': '<sup>4</sup>', '⁵': '<sup>5</sup>', '⁶': '<sup>6</sup>', '⁷': '<sup>7</sup>',
        '⁸': '<sup>8</sup>', '⁹': '<sup>9</sup>', '°': '<sup>o</sup>', 'º': '<sup>o</sup>',
        'ª': '<sup>a</sup>'
    }
    for char, replacement in sub_map.items():
        text = text.replace(char, replacement)
    for char, replacement in sup_map.items():
        text = text.replace(char, replacement)
    return text


def format_paragraphs_for_canva(text: str) -> str:
    if not text:
        return ""
    blocks = re.split(r'\n\s*\n', text)
    processed_blocks = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if (block.startswith("---") or 
            any(line.strip().startswith(("#", "-", "*", "[BOX]", "[/BOX]", "[IMG:")) for line in lines)):
            processed_blocks.append(block)
        else:
            joined = " ".join(line.strip() for line in lines if line.strip())
            processed_blocks.append(joined)
    return "\n\n".join(processed_blocks)


def sanitize_markdown(text: str) -> str:
    if not text:
        return ""
    clean = text.strip()
    
    # 1. Remove cercas de código markdown (```markdown ... ```)
    clean = re.sub(r'^```markdown\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^```\s*', '', clean)
    clean = re.sub(r'\s*```$', '', clean)
    clean = clean.strip()
    
    # 2. Remove preâmbulos antes do cabeçalho YAML
    yaml_start = clean.find("---")
    if yaml_start != -1 and yaml_start > 0:
        before_yaml = clean[:yaml_start].strip()
        if before_yaml:
            print(f"✂️ Sanitizador Python: Removendo preâmbulo antes do YAML: {before_yaml[:100]}...")
            clean = clean[yaml_start:].strip()
            
    # 3. Remove blockquotes (>) do início de cada linha
    lines = clean.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            line = re.sub(r'^(\s*>)+', '', line).strip()
        clean_lines.append(line)
    clean = "\n".join(clean_lines)
    
    # 4. Substituição de glifos especiais (graus e subscritos químicos)
    clean = replace_special_symbols(clean)
    
    # 5. Formatação de parágrafos contínuos para compatibilidade com Canva
    clean = format_paragraphs_for_canva(clean)
        
    return clean



def load_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def generate_content_with_retry(client, model, contents, max_retries=5, initial_backoff=2, config=None, pdf_path=None):
    """
    Executa client.models.generate_content com lógica de retentativa exponencial
    e rotação de chaves/clientes de API para lidar com alta demanda e limites de taxa.
    Garante que o upload de arquivos PDF seja feito pelo mesmo cliente ativo na tentativa.
    """
    backoff = initial_backoff
    
    current_idx = 0
    if client in clients:
        current_idx = clients.index(client)
        
    for attempt in range(max_retries):
        active_client = clients[current_idx % len(clients)]
        uploaded_file = None
        try:
            actual_contents = contents
            if pdf_path:
                print(f"📤 Gemini API (Chave {current_idx % len(clients) + 1}): Fazendo upload do PDF nativo...")
                uploaded_file = active_client.files.upload(file=pdf_path)
                
                # Aguarda o processamento do arquivo
                state = uploaded_file.state
                check_attempts = 0
                while state == "PROCESSING" and check_attempts < 10:
                    print("⏳ Gemini API: Processando arquivo...")
                    time.sleep(2)
                    uploaded_file = active_client.files.get(name=uploaded_file.name)
                    state = uploaded_file.state
                    check_attempts += 1
                    
                if state != "ACTIVE":
                    raise ValueError(f"O arquivo enviado para o Gemini está com estado inválido: {state}")
                
                # Junta o arquivo temporário com as instruções do prompt
                actual_contents = [uploaded_file, contents]

            response = active_client.models.generate_content(
                model=model,
                contents=actual_contents,
                config=config
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
            
            # Se houver múltiplas chaves configuradas, rotaciona para a próxima
            if len(clients) > 1:
                current_idx += 1
                print(f"🔄 Gemini: Rotacionando para a chave API {current_idx % len(clients) + 1} devido a erro temporário: {err_msg}")
            
            # Aplica backoff exponencial com jitter
            sleep_time = backoff + random.uniform(0, 1)
            print(f"⚠️ Gemini: Erro temporário ({err_msg}). Tentativa {attempt + 1}/{max_retries} falhou. Retentando em {sleep_time:.2f}s...")
            time.sleep(sleep_time)
            backoff *= 2 # Dobra o intervalo
        finally:
            if uploaded_file:
                try:
                    print(f"🗑️ Gemini API: Removendo arquivo temporário: {uploaded_file.name}")
                    active_client.files.delete(name=uploaded_file.name)
                except Exception as ex:
                    print(f"⚠️ Gemini API: Não foi possível deletar o arquivo temporário: {ex}")




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
    return sanitize_markdown(response.text)


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
    return sanitize_markdown(response.text)


def process_content_to_style(content_input: str, is_pdf: bool = False, model: str = None) -> str:
    """
    Processa o conteúdo (bruto ou PDF) em um único passo otimizado,
    reescrevendo e polindo no padrão Evolux.
    """
    if model is None:
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

    base_prompt = load_prompt()
    
    # Adicionamos diretrizes de revisão e sanitização no prompt do sistema
    system_instruction = (
        f"{base_prompt}\n\n"
        "Você é um Revisor Editorial Sênior da Evolux Academy especializado em design instrucional e revisão ortográfica.\n"
        "Sua missão é gerar o conteúdo em Markdown impecável, formatado e revisado de primeira, seguindo regras rígidas de saída:\n\n"
        "REGRA ABSOLUTA DE SAÍDA:\n"
        "- Sua resposta deve conter EXCLUSIVAMENTE o texto Markdown revisado, começando diretamente com o bloco YAML (---) do cabeçalho.\n"
        "- NUNCA inclua preâmbulos, explicações, comentários sobre a revisão, ou qualquer texto introdutório antes do conteúdo.\n"
        "- A primeira linha da sua resposta DEVE ser exatamente '---' (o início do cabeçalho YAML).\n"
        "- Se o rascunho contiver blocos de código Markdown (```markdown ... ```), remova esses delimitadores e retorne apenas o conteúdo interno.\n\n"
        "DIRETRIZES DE REVISÃO E FORMATAÇÃO:\n"
        "1. CORREÇÃO GRAMATICAL: Corrija quaisquer erros ortográficos, concordância e digitação.\n"
        "2. NÃO UNIR CABEÇALHOS AO TEXTO: Os cabeçalhos (#, ##, ###, ####) devem sempre ficar em suas próprias linhas, isolados por uma linha em branco.\n"
        "3. QUEBRAS DE LINHA PARA O CANVA: Parágrafos normais devem ser contínuos (linhas unidas com espaços simples). NUNCA use quebras de linha simples no meio de um parágrafo. Separe parágrafos estritamente com exatamente duas quebras de linha (\\n\\n).\n"
        "4. EVITAR SIMBOLOS TOFU (QUADRADOS): NUNCA utilize caracteres Unicode de subscrito/sobrescrito especiais (como ₂ ou ³) ou símbolo de graus (°) direto se puderem quebrar em fontes padrão. Em vez disso, use tags HTML que o ReportLab suporta nativamente:\n"
        "   - Use <sub> e </sub> para subscritos. Exemplo: H<sub>2</sub>O, CO<sub>2</sub>.\n"
        "   - Use <sup> e </sup> para sobrescritos e graus Celsius. Exemplo: 35<sup>o</sup>C ou 10<sup>a</sup> aula.\n"
        "5. SANITIZAÇÃO DE MARCAÇÕES: Garanta que marcações [BOX] e [/BOX] fiquem puras em linhas isoladas. Tags de imagens devem usar [IMG:nome_imagem.png] (Descrição detalhada).\n"
        "6. PROIBIÇÃO DE BLOCKQUOTES (>): Nunca use o caractere '>' no início de linhas. Se necessário, coloque o texto dentro de um bloco [BOX].\n"
        "7. Sem emojis no corpo do texto final e respeitando estritamente a estrutura acadêmica."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2
    )

    if is_pdf:
        # Se for PDF, passamos o caminho do arquivo no parâmetro pdf_path
        # E contents passa a ser a instrução de leitura
        contents = "\n\nInstrução: Por favor, leia o PDF fornecido acima e reescreva-o de acordo com as diretrizes do sistema."
        response = generate_content_with_retry(
            client=client,
            model=model,
            contents=contents,
            config=config,
            pdf_path=content_input
        )
    else:
        contents = (
            "INSTRUÇÃO ADICIONAL: Reescreva e adapte o conteúdo bruto fornecido abaixo ao padrão especificado no sistema.\n\n"
            f"CONTEÚDO BRUTO A SER REESCRITO:\n{content_input}"
        )
        response = generate_content_with_retry(
            client=client,
            model=model,
            contents=contents,
            config=config
        )
        
    return sanitize_markdown(response.text)


