# Trader Agent (PCE) - Demo v0

Agente independente em `agents/trader`, sem integração com `pce-os`.

## Objetivo
Pipeline completa em camadas PCE:
- EPL: ingestão/validação de candles 1h/4h.
- ISI: integração de estado + features técnicas.
- VEL: scoring de oportunidade/risco/qualidade.
- SM: persistência em SQLite via `pce-core` StateManager.
- DE: gates fixos (macro -> modelo -> guardrails).
- AO: execução mock (`MockBroker`) com fee/slippage determinísticos.
- AFS: labels Triple-Barrier, treino supervisionado leve, walk-forward e registry local.
- Expression Layer: LLM apenas para explicação (não altera decisão).
- UI Web local (FastAPI + WebSocket + HTML/JS) para observabilidade e controle em tempo real.

## Como rodar
### 1) Replay determinístico de histórico
```bash
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv
```

### 2) Treino batch
```bash
python agents/trader/cli.py train --csv agents/trader/data/sample_features.csv
```

### 3) Demo live (market data real)
```bash
python agents/trader/cli.py live-demo --output agents/trader/artifacts/live_demo.json
```

### 4) UI local completa (backend + frontend)
```bash
python agents/trader/cli.py ui --port 8787
```
Abra em: `http://127.0.0.1:8787`.

> Dependências adicionadas e justificativa:
> - `fastapi` e `uvicorn` para servidor HTTP + WebSocket com baixo acoplamento.
> - Frontend sem framework pesado (HTML/CSS/JS vanilla), reduzindo bundle e setup.

## Dashboard UI
A UI serve seis áreas (tabs):
1. **Overview**: KPIs (CCI-F, mode, equity, drawdown, trades, decisões) + alertas.
2. **Market & Regime**: visão por símbolo/timeframe com features e regime.
3. **Decisions**: lista de decisões com detalhes (gate_results, explanation e payload bruto).
4. **Execution / Portfolio**: posições, fills/trades e PnL.
5. **Models & Learning**: modelo ativo, registry e disparo de treino.
6. **System / Logs**: stream em tempo real via websocket + downloads de snapshot.

## API (contrato da UI)
### Health
- `GET /api/health`

### Estado consolidado
- `GET /api/state`

### Decisões / TradePlans
- `GET /api/decisions?limit=200`

### Trades e portfólio
- `GET /api/trades?limit=200`
- `GET /api/portfolio`

### Modelos e aprendizado
- `GET /api/models`
- `POST /api/train`
- `GET /api/train/status?run_id=...`

### Controle do runtime
- `POST /api/control/start`
- `POST /api/control/stop`
- `POST /api/control/pause`
- `POST /api/control/resume`
- `POST /api/control/reset` (body obrigatório: `{"confirm": true}`)
- `POST /api/control/config`
  - validações principais:
    - `threshold` entre `0.50` e `0.80`
    - limites de risco e fee/slippage com range seguro

### Realtime
- `WS /ws/events`
  - eventos: `candle`, `decision`, `execution`, `metrics`, `log`

## Mocking e fallback
- A UI funciona mesmo sem LLM e sem internet.
- Sem dados reais de mercado, gera candles determinísticos de fallback.
- Campos indisponíveis são marcados como mock no frontend (ex.: equity curve v0).
- Para desabilitar Binance explicitamente:
```bash
TRADER_UI_DISABLE_BINANCE=1 python agents/trader/cli.py ui --port 8787
```

## Persistência e observabilidade
- Estado persistido: `agents/trader/artifacts/trader_state.db`
- Logs estruturados de decisões: `agents/trader/artifacts/logs/decisions.jsonl`
- Cache leve de UI: `agents/trader/artifacts/ui_cache.json`
- Modelos: `agents/trader/artifacts/model-*.json`

## Troubleshooting
### Porta ocupada
```bash
python agents/trader/cli.py ui --port 8788
```

### Sem internet / Binance indisponível
Use fallback local:
```bash
TRADER_UI_DISABLE_BINANCE=1 python agents/trader/cli.py ui --port 8787
```

### Sem LLM
Comportamento padrão já é fallback seguro, sem bloquear runtime/UI.

### WebSocket não atualiza
- Verifique se o runtime foi iniciado via botão **Start** ou endpoint `/api/control/start`.
- Confira logs em **System / Logs**.

## Testes
```bash
python -m pytest agents/trader/tests -q
```

## Segurança
- Não usar corretora real nessa versão.
- Não comitar segredos (`.env`, keys, tokens).
- Endpoints de controle com validação básica de input.
- Bind padrão em `127.0.0.1`.
