# PCE-OS UI (Control Room)

Interface web para monitorar o PCE-OS multi-agente em tempo real:

- Overview de KPIs e estado de policy
- Live Feed com SSE + fallback para polling
- Approvals com approve/reject/override
- Twin snapshot + auditoria
- Agents status cards

## Pré-requisitos

- Node.js 20+
- Backend FastAPI local

## Rodando backend + UI

1. Backend API (porta 8080):

```bash
uvicorn pce_api.main:app --reload --port 8080
```

2. UI:

```bash
cd apps/ui-os
npm i
npm run dev
```

## Variáveis de ambiente

### UI

- `VITE_API_BASE_URL` (default `http://127.0.0.1:8080`)

Exemplo:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```

### Backend

- SSE (`GET /v1/stream/os`) já está habilitado por padrão no servidor.
- LLM de agentes continua **server-side** (não exposto no frontend).
