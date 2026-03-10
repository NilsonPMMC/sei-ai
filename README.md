# SEI AI — Motor de Triagem e Painel SGDLe

Sistema de triagem inteligente de processos (SEI) com RAG (Retrieval-Augmented Generation), classificação de serviços e painel web para aprovação human-in-the-loop.

## Estrutura do repositório

| Pasta | Descrição |
|-------|-----------|
| **motor-triagem-ia** | Backend FastAPI: RAG (Groq + embeddings), fila de processos, proxy Sinapse |
| **sinapse-frontend** | Frontend Vue 3 + Vite + Tailwind: painel de triagem (cards/tabela), filtros, unidade destino |

## Pré-requisitos

- **Python 3.11+** (backend)
- **Node.js 18+** (frontend)
- **PostgreSQL** com extensão **pgvector** (bancos: `sinapse`, `sei_ai`)
- **Groq API Key** (LLM)
- **API de embeddings** (configurável)

## Configuração

### Backend (motor-triagem-ia)

```bash
cd motor-triagem-ia
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# Edite .env com: GROQ_API_KEY, SINAPSE_DB_URL, SEI_AI_DB_URL, EMBEDDING_API_URL, SINAPSE_API_BASE
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (sinapse-frontend)

```bash
cd sinapse-frontend
npm install
npm run dev
```

Acesse o painel em **http://localhost:5173**. A API do backend deve estar em **http://localhost:8000**.

### Variáveis de ambiente (backend)

Consulte `motor-triagem-ia/.env.example`. Principais:

- `GROQ_API_KEY` — chave da API Groq (LLM)
- `SINAPSE_DB_URL`, `SEI_AI_DB_URL` — conexões PostgreSQL
- `EMBEDDING_API_URL` — endpoint de embeddings
- `SINAPSE_API_BASE` — base da API Sinapse (Carta de Serviços; usado pelo proxy)

## Funcionalidades

- **Triagem RAG**: extração de intenção → embedding → busca vetorial (Top 3) → inferência Groq com rota de fuga para “Processo Interno / Não Mapeado”
- **Fila de processos**: listagem, filtros (status, unidade), aprovar/devolver com **unidade destino** (human-in-the-loop)
- **Integração Sinapse**: proxy para unidades/serviços (evita CORS), filtro e exibição de Unidade Responsável
- **Painel**: visualização em cards ou tabela, anexos identificados, seleção de unidade antes de aprovar

## API (backend)

- `GET /v1/fila` — lista processos pendentes
- `POST /v1/fila` — cria/atualiza processo (RPA)
- `PATCH /v1/fila/{numero_sei}/acao` — aprovar (`unidade_destino_id`) ou devolver
- `POST /v1/triagem/classificar` — classificação RAG (texto → serviço + resumo + documentação)
- `GET /v1/sinapse/unidades` — proxy unidades Sinapse
- `GET /v1/sinapse/servicos` — proxy serviços Sinapse

## Licença

Uso interno / PoC.
