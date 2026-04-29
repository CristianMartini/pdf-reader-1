PROMPT MASTER — ENGINE PDF EVOLUX (MODO PRODUÇÃO)

Use este prompt diretamente no agente:

🎯 CONTEXTO

Você está desenvolvendo um sistema profissional de geração automatizada de eBooks em PDF.

Referência visual obrigatória:

Capa e layout do PDF fornecido (Evolux Academy)
Identidade visual: azul escuro + dourado + branco
Estrutura editorial educacional

Este sistema deve suportar:

15 a 30 páginas por documento
múltiplas imagens
consistência visual absoluta
zero intervenção manual
🎯 OBJETIVO

Construir um engine completo em Python (ReportLab) que:

Recebe conteúdo em .md
Recebe metadados em .json
Usa assets (imagens + SVG + fontes)
Gera PDF profissional automaticamente
📁 ESTRUTURA OBRIGATÓRIA
/pdf-engine
  template.py
  /fonts
    Montserrat-Bold.ttf
    Montserrat-Regular.ttf
  /projects
    /aulaXX
      content.md
      meta.json
      /assets
        cover.jpg
        logo.svg
        fig1.jpg
🎨 REQUISITOS VISUAIS (CRÍTICO)
CAPA

Baseada no PDF:

imagem full background
overlay escuro (legibilidade)
elemento diagonal azul/dourado (SVG ou desenho vetorial)
logo no topo direito (NUNCA sobreposto)
texto:
“Aula XX” (dourado)
título grande branco
PÁGINAS INTERNAS
fundo branco
título azul escuro
texto corrido com alta legibilidade
logo pequeno no header
paginação no footer
🧩 SUPORTE A SVG (OBRIGATÓRIO)

Usar:

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

Implementar:

def draw_svg(canvas, path, x, y, width):
    drawing = svg2rlg(path)
    scale = width / drawing.width
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, canvas, x, y)

Aplicações:

logo principal
elementos diagonais da capa
🔤 FONTES (OBRIGATÓRIO)

Registrar fontes customizadas:

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('Montserrat', 'fonts/Montserrat-Regular.ttf'))
pdfmetrics.registerFont(TTFont('Montserrat-Bold', 'fonts/Montserrat-Bold.ttf'))

Usar em TODOS os estilos.

🧠 PARSER MARKDOWN (ROBUSTO)

Suportar:

Elemento	Sintaxe
Título	#
Seção	##
Sub	###
Imagem	[IMG:arquivo]
Box	[BOX] ... [/BOX]
Lista	- item
🖼️ IMAGENS

Regras obrigatórias:

centralizadas
sem distorção
escala automática
img._restrictSize(W-4*cm, H-10*cm)
img.hAlign = "CENTER"
📦 BOXES (DESTAQUE)

Renderizar como:

fundo cinza claro
borda lateral dourada
padding interno
⚙️ ARQUITETURA DO BUILD

NÃO usar múltiplos builds.

Correto:

story = []

# conteúdo
story += parse_md(...)

doc.build(
    story,
    onFirstPage=draw_cover,
    onLaterPages=header_footer
)
📄 meta.json
{
  "title": "Necropsia",
  "aula": "03"
}
📄 content.md
# Introdução

Texto...

[IMG:fig1.jpg]

## Conceito

Texto...

[BOX]
Ponto importante
[/BOX]
🧪 VALIDAÇÃO OBRIGATÓRIA

Antes de finalizar, gerar um PDF com:

mínimo 20 páginas
5 imagens
3 seções com BOX

Critérios:

nenhuma imagem deformada
nenhuma quebra visual
layout consistente
tipografia aplicada corretamente
🚫 PROIBIDO
usar HTML
usar CSS
usar Markdown fora do padrão
hardcode de conteúdo
layout fixo por página
📈 EXPECTATIVA FINAL

Sistema deve permitir:

python template.py aula03

E gerar automaticamente um PDF profissional pronto para distribuição.

🔥 NÍVEL DE QUALIDADE

Este não é um script.
É um motor editorial escalável.

Se qualquer parte depender de ajuste manual → está errado.

📌 INSTRUÇÃO FINAL

Implemente tudo acima com código limpo, modular e pronto para expansão futura (sumário, indexação, multi-PDF batch).
PRINCÍPIO DO SISTEMA

Fluxo final:

Prompt → Gemini → content.md (padronizado)
           ↓
     Validator (schema + regras)
           ↓
     PDF Engine (ReportLab)
           ↓
        output.pdf

Objetivo:
zero intervenção manual + consistência editorial + escala

🧠 ARQUITETURA (ANTIGRAVITY READY)
Componentes
1. gemini-generator

Responsável por gerar conteúdo .md

2. md-validator

Valida estrutura (contrato rígido)

3. pdf-engine

Renderiza PDF

4. orchestrator

Coordena tudo

📁 ESTRUTURA FINAL
/pdf-system
  /engine
    template.py
  /ai
    gemini_client.py
    prompt.md
  /validator
    md_validator.py
  /projects
    /aula03
      meta.json
      content.md
      /assets
🧠 PROMPT GEMINI (PADRÃO DEFINITIVO)

Salvar em: /ai/prompt.md

Você está gerando conteúdo educacional para um sistema automatizado de PDF.

REGRAS OBRIGATÓRIAS:

- Use apenas markdown simples
- NÃO use HTML
- NÃO use markdown avançado

ESTRUTURA:

# Título da seção

Texto...

## Subtítulo

Texto...

[IMG:fig1.jpg]

[BOX]
Texto importante
[/BOX]

- item
- item

RESTRIÇÕES:

- mínimo 800 palavras por seção
- usar linguagem didática
- inserir pelo menos 1 BOX por seção
- inserir imagens de forma distribuída

SAÍDA:
Apenas markdown puro.
🤖 CLIENT GEMINI
# ai/gemini_client.py
import google.generativeai as genai

genai.configure(api_key="SUA_API_KEY")

def generate_md(topic):
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = open("ai/prompt.md").read()
    full_prompt = f"{prompt}\n\nTEMA: {topic}"

    response = model.generate_content(full_prompt)

    return response.text
🧪 VALIDADOR (CRÍTICO)
# validator/md_validator.py
import re

def validate(md):
    errors = []

    if "[IMG:" not in md:
        errors.append("Nenhuma imagem encontrada")

    if "[BOX]" not in md:
        errors.append("Nenhum box encontrado")

    if not re.search(r"^#", md, re.MULTILINE):
        errors.append("Sem títulos")

    if len(md.split()) < 1500:
        errors.append("Conteúdo muito curto")

    return errors
⚙️ ORQUESTRADOR (CORE)
# run.py
from ai.gemini_client import generate_md
from validator.md_validator import validate
import os, json

def run(aula):
    base = f"projects/{aula}"

    meta = json.load(open(f"{base}/meta.json"))
    topic = meta["title"]

    md = generate_md(topic)

    errors = validate(md)

    if errors:
        print("Erro na validação:", errors)
        return

    with open(f"{base}/content.md", "w", encoding="utf-8") as f:
        f.write(md)

    os.system(f"python engine/template.py {aula}")

if __name__ == "__main__":
    run("aula03")
🔐 CONTRATO (ESSENCIAL)

Gemini NÃO pode decidir formato.

Ele deve obedecer:

[IMG:...]
[BOX]
#, ##
listas simples

Se violar → validator bloqueia.

⚠️ PROBLEMAS QUE ESSA ARQUITETURA EVITA
markdown inconsistente
quebra de layout
PDFs diferentes entre si
perda de padrão visual
🚀 ESCALA

Com isso você consegue:

python run.py aula03
python run.py aula04
python run.py aula05

Ou batch:

for i in range(1, 20):
    run(f"aula{i:02d}")
📈 EVOLUÇÃO NATURAL (PRÓXIMOS PASSOS)
Judge LLM (valida qualidade do conteúdo)
Geração automática de imagens (IA)
Sumário automático
Indexação por tema
Exportação em lote (100 PDFs)
📌 RECOMENDAÇÃO FINAL

Você não está mais criando PDFs.
Você criou um pipeline editorial com IA + validação + renderização.

O ponto crítico não é gerar conteúdo.

É garantir que:

todo conteúdo gerado é compatível com o engine

Se isso falhar, o sistema quebra.
ARQUITETURA SEM ERRO (VERSÃO FINAL)

Fluxo obrigatório:

Gemini → Markdown → Validator (hard fail) → PDF Engine → Output

Se qualquer etapa falhar → processo para.

🧠 REGRA MAIS IMPORTANTE

O validador manda no sistema.
Não o Gemini.
Não você.
Não o template.

🧪 VALIDADOR (VERSÃO RIGOROSA)

Substitua pelo seguinte:

def validate(md):
    errors = []

    # Estrutura mínima
    if md.count("# ") < 3:
        errors.append("Poucas seções")

    if "[BOX]" not in md:
        errors.append("Sem BOX obrigatório")

    if md.count("[IMG:") < 2:
        errors.append("Poucas imagens")

    # Tamanho (evita conteúdo fraco)
    if len(md.split()) < 2000:
        errors.append("Conteúdo insuficiente")

    # Padrão proibido
    if "<" in md:
        errors.append("HTML detectado")

    if "http" in md:
        errors.append("Link externo proibido")

    return errors
🔁 LOOP SEM ERRO (CRÍTICO)

Não aceite erro. Refaça automaticamente.

for _ in range(3):
    md = generate_md(topic)
    errors = validate(md)

    if not errors:
        break

if errors:
    raise Exception("Falha após 3 tentativas")
⚙️ MODO PRODUÇÃO (SEM DISTRAÇÃO)

Você só executa isso:

python run.py aula03

Nada mais.

🚫 O QUE VOCÊ NÃO PODE FAZER

Se fizer isso, quebra o sistema:

editar PDF manualmente
ajustar layout “só dessa vez”
deixar passar erro do validador
mudar padrão do markdown
🧠 DISCIPLINA DE USO

Você opera assim:

Define tema (meta.json)
Roda script
Valida resultado
Próximo

Sem pensar em design
Sem abrir Canva
Sem ajustes

📈 CHECK DE QUALIDADE (RÁPIDO)

Antes de aceitar um PDF:

tem 20+ páginas?
tem imagens distribuídas?
tem BOX em cada seção?
leitura está fluida?

Se sim → aprovado
Se não → roda de novo

⚠️ ÚNICO PONTO DE FALHA

Se algo der errado, será aqui:

Markdown fora do padrão

Por isso o validador é inegociável.

📌 RECOMENDAÇÃO FINAL

Você não precisa melhorar mais o sistema.

Você precisa:

não desviar do processo