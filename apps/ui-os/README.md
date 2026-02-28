# PCE-OS UI

Cockpit front-end para o domínio OS (robótica), cobrindo MVP de:

- Overview operacional
- Gestão de approvals (approve/reject)
- Visualização do Digital Twin

## Pré-requisitos

- Node.js 20+
- API FastAPI em execução local

## Rodando em desenvolvimento

1. Suba a API:

```bash
uvicorn pce_api.main:app --reload --port 8080
```

2. Rode a UI:

```bash
npm i
npm run dev
```

## Configuração de API

A UI chama sempre `/api/...` no cliente e usa proxy do Vite para apontar para o backend.

- Variável suportada: `VITE_API_BASE_URL`
- Default: `http://127.0.0.1:8080`

Exemplo:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```
