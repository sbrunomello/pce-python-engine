# Trader Agent (PCE) - Demo v0 (Sprint 1: PCE Foundation)

Agente independente em `agents/trader`, sem integração com `pce-os`, usando somente `pce-core` (StateManager).

## Objetivo
Pipeline completa em camadas PCE:
- EPL: ingestão/validação de candles 1h/4h.
- ISI: integração de estado + features técnicas.
- VEL: scoring de oportunidade/risco/qualidade.
- SM: persistência em SQLite via `pce-core` StateManager.
- DE: gates fixos (macro -> modelo -> guardrails) + ações mínimas `ENTER_LONG` / `EXIT` / `NO_TRADE`.
- AO: execução mock (`MockBroker`) com BUY/SELL, fee/slippage determinísticos e PnL realizado/não realizado.
- AFS: labels Triple-Barrier, treino supervisionado leve, walk-forward e registry local.
- Event Ledger append-only para auditoria/replay determinístico.

## Event Envelope padrão
Todos os eventos emitidos pelo trader seguem `EventEnvelope` com:
- `event_id`, `event_type`, `ts`, `source`, `payload`
- `correlation_id`, `causation_id`, `actor`, `version`

Tipos padronizados utilizados:
- `market.candle.closed`
- `state.integrated`
- `decision.trade_plan.created`
- `execution.order.filled`
- `execution.skipped`
- `metrics.updated`
- `guardrail.locked`
- `guardrail.unlocked`
- `system.data_integrity.degraded`

Cadeia causal obrigatória:
- candle -> decision (`decision.causation_id = candle.event_id`)
- decision -> execution (`execution.causation_id = decision.event_id`)

## Event Ledger (append-only)
- Caminho padrão: `agents/trader/artifacts/ledger/events.jsonl`
- Fonte de verdade para auditoria/replay/UI.
- Escreve 1 JSON por linha, sem mutação retroativa.

### Comandos de inspeção
```bash
python agents/trader/cli.py ledger tail --limit 200
python agents/trader/cli.py ledger query --type decision.trade_plan.created --symbol BTCUSDT --limit 50
```

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

## Resets diários e mensais (UTC)
No runtime, ao virar período:
- Mudança de dia:
  - reset `trades_total_day` e `trades_by_asset_day`
  - `day_start_equity = equity`
  - persistência de `last_day = YYYY-MM-DD`
- Mudança de mês:
  - `month_start_equity = equity`
  - persistência de `last_month = YYYY-MM`

`dd_day` e `dd_month` são sempre calculados sobre os `start_equity` do período atual.

## Portfolio / Equity / PnL
Estado com chaves estáveis:
- `state["prices"]["BTCUSDT"]`
- `state["portfolio"]["positions"]["BTCUSDT"] = {qty, avg_price}`
- `state["portfolio"]["realized_pnl"]`, `state["portfolio"]["unrealized_pnl"]`
- `state["limits"]["last_day"]`, `last_month`, `day_start_equity`, `month_start_equity`

Fórmulas:
- `equity = cash + Σ(qty_symbol * last_price_symbol)`
- `unrealized_pnl = Σ((last_price - avg_price) * qty)`
- `realized_pnl` atualizado em SELL/EXIT
- SELL acima da posição é bloqueado (v0)

## Limitações da versão
- Ainda é demo: **sem corretora real**.
- Ainda sem stop/take-profit automáticos (Sprint 2/3).
- Dependências continuam leves (sem libs pesadas novas).

## Persistência e observabilidade
- Estado persistido: `agents/trader/artifacts/trader_state.db`
- Ledger de eventos: `agents/trader/artifacts/ledger/events.jsonl`
- Logs estruturados de decisões: `agents/trader/artifacts/logs/decisions.jsonl`
- Modelos: `agents/trader/artifacts/model-*.json`

## Testes
```bash
pytest agents/trader/tests -q
```
