# Skills do Projeto — PDF Engine Evolux

Este arquivo lista as skills do Antigravity instaladas e ativas para este projeto.

## Skills Ativas

### 🐍 python-pro
**Descrição:** Python 3.12+ com boas práticas modernas, type hints, async, pyproject.toml.
**Uso no projeto:** base de todo o código (template.py, gemini_client.py, md_validator.py, run.py)

### 🤖 gemini-api-dev
**Descrição:** Integração com a Gemini API (google-genai SDK). Geração de conteúdo, structured output.
**Uso no projeto:** `ai/gemini_client.py` — geração automática de content.md via Gemini

### 📄 documentation
**Descrição:** Geração de documentação técnica, README, guias de uso.
**Uso no projeto:** Documentação do engine, README do projeto, guia do formato .md

### 🧪 tdd-workflow
**Descrição:** Ciclo RED-GREEN-REFACTOR. Testes com pytest.
**Uso no projeto:** Testes do validator, do parser e do pipeline de build

### 🛠️ bash-scripting
**Descrição:** Scripts de automação shell/bash para batch processing.
**Uso no projeto:** Scripts de execução em lote (`for i in range(1,20): run(...)`)

### 🔍 systematic-debugging
**Descrição:** Debugging estruturado para erros inesperados em pipelines.
**Uso no projeto:** Diagnóstico de quebras no build PDF, erros do ReportLab

### 🏗️ concise-planning
**Descrição:** Planejamento em checklist atômico antes de implementar.
**Uso no projeto:** Planejamento de fases (build único, parser robusto, capa, validador)

### 📐 architect-review
**Descrição:** Revisão de arquitetura de software escalável.
**Uso no projeto:** Validação da arquitetura: gemini → validator → engine → output

---

## Dependências Python do Projeto

```
reportlab
svglib
google-genai
```

## Instalação

```bash
pip install reportlab svglib google-genai
```

## Estrutura do Projeto (Conforme Instruções)

```
/pdf-system
  run.py                  ← orquestrador principal
  /engine
    template.py           ← PDF engine (ReportLab)
  /ai
    gemini_client.py      ← cliente Gemini API
    prompt.md             ← prompt padrão para o Gemini
  /validator
    md_validator.py       ← validador rigoroso do markdown
  /fonts
    Montserrat-Bold.ttf
    Montserrat-Regular.ttf
  /projects
    /aulaXX
      meta.json
      content.md
      /assets
        cover.jpg
        logo.svg
        fig1.jpg
```
