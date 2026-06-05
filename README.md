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

## 🌐 Arquitetura Web & Persistência em Nuvem (Bypass da Vercel)

Para hospedar o editor web e a fila de inteligência artificial de forma 100% gratuita na Vercel sem sofrer com o limite de request payload de **4.5 MB** do plano gratuito, a aplicação utiliza uma arquitetura de **Direct-to-Storage Upload**:

1. **Signed URLs v4 (`PUT`)**: Quando um arquivo (PDF antigo, documento MD ou imagem) é enviado pela interface, o front-end solicita uma URL Assinada de curta duração (15 minutos) ao backend.
2. **Upload Direto**: O navegador realiza um `PUT` binário diretamente para a URL fornecida (apontando para `storage.googleapis.com`), enviando o arquivo sem trafegar pela infraestrutura serverless da Vercel.
3. **CORS Dinâmico**: O backend gerencia e configura automaticamente as regras de CORS (Cross-Origin Resource Sharing) no bucket do Firebase Storage no momento da inicialização do app.
4. **Sincronização Serverless**: Após o upload direto ser concluído pelo navegador, o backend é notificado e baixa o arquivo do Firebase Storage para o disco temporário do container serverless (`/tmp`) apenas para realizar o processamento com Gemini AI ou compilar o PDF (pypdf/ReportLab).

### Fallback Local/Offline
Caso a chave do Firebase não esteja configurada no ambiente (como ao rodar localmente sem internet ou sem `serviceAccountKey.json`), o editor reverte automaticamente para o **modo de upload tradicional** via rota Flask (com verificação local de tamanho).

### Variáveis de Ambiente Necessárias (Produção Vercel)
Para ativar a persistência e uploads ilimitados na Vercel, defina:
- `FIREBASE_CREDENTIALS`: A string JSON completa da chave de conta de serviço (Service Account Key) do seu projeto Firebase.

---

## Skills Antigravity Utilizadas

- `python-pro` — código Python moderno e robusto
- `gemini-api-dev` — integração com Gemini (SDK google-genai)
- `tdd-workflow` — testes do validator e parser
- `systematic-debugging` — diagnóstico de erros no build
- `architect-review` — validação da arquitetura do pipeline

