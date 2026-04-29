# PDF Engine Evolux — Sistema Editorial Automatizado

Motor profissional de geração de eBooks/PDFs educacionais com Python + ReportLab + Gemini AI.

## 🎯 Objetivo

```
Prompt → Gemini → content.md → Validator → PDF Engine → output.pdf
```

Zero intervenção manual. Consistência editorial absoluta. Escala de 1 a 100 PDFs.

## 📦 Instalação

```bash
pip install -r requirements.txt
```

**Dependências:**
- `reportlab` — renderização PDF
- `svglib` — suporte a SVG (logo + elementos diagonais)
- `google-genai` — geração de conteúdo com Gemini

## ⚙️ Configuração

Defina sua chave da Gemini API como variável de ambiente:

```bash
# Windows
set GEMINI_API_KEY=sua_chave_aqui

# Linux/Mac
export GEMINI_API_KEY=sua_chave_aqui
```

## 🚀 Uso

### Gerar um PDF com conteúdo automático (Gemini)
```bash
python run.py aula03
```

### Gerar PDF a partir de content.md existente
```bash
python engine/template.py aula03
```

### Gerar em lote (aula01 até aula10)
```bash
python run.py batch 1 10
```

## 📁 Estrutura do Projeto

```
/pdf-system
  run.py                   ← orquestrador principal
  requirements.txt
  /engine
    template.py            ← PDF engine (ReportLab)
  /ai
    gemini_client.py       ← cliente Gemini API
    prompt.md              ← prompt padrão
  /validator
    md_validator.py        ← validador rigoroso
  /fonts
    Montserrat-Bold.ttf    ← (opcional, usa Helvetica como fallback)
    Montserrat-Regular.ttf
  /projects
    /aula03
      meta.json            ← {"title": "...", "aula": "03"}
      content.md           ← conteúdo em markdown
      /assets
        cover.jpg          ← imagem de capa
        logo.svg ou .png   ← logo da instituição
        fig1.jpg           ← figuras do conteúdo
```

## 📄 Formato do content.md

```markdown
# Título Principal

Texto da seção...

## Subtítulo

Texto...

[IMG:fig1.jpg]

[BOX]
Ponto importante ou resumo crítico.
[/BOX]

- Item de lista
- Outro item
```

## ✅ Critério de Aprovação

- [ ] 20+ páginas renderizadas sem quebra visual
- [ ] Imagens centralizadas sem distorção
- [ ] BOX com borda dourada em cada seção
- [ ] Capa com overlay, diagonal dourada e logo
- [ ] Tipografia consistente em todas as páginas
- [ ] Zero ajuste manual necessário

## Skills Antigravity Utilizadas

- `python-pro` — código Python moderno e robusto
- `gemini-api-dev` — integração com Gemini (SDK google-genai)
- `tdd-workflow` — testes do validator e parser
- `systematic-debugging` — diagnóstico de erros no build
- `architect-review` — validação da arquitetura do pipeline
