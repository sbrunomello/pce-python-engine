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

## Configuração
Ajustar em `trader_plugins/config.py`:
- ativos (`BTCUSDT`, `ETHUSDT`, `SOLUSDT` default)
- threshold inicial `p_win >= 0.60`
- limites de risco (0,5% por trade, DD diário/mensal, máximo de trades)
- paths de artefatos e DB.

Também é possível usar variáveis de ambiente do OpenRouter para explicações LLM (opcional).
Sem chave, o agente usa fallback local seguro.

## Outputs e observabilidade
- Estado persistido: `agents/trader/artifacts/trader_state.db`
- Logs estruturados: `agents/trader/artifacts/logs/decisions.jsonl`
- Modelo(s): `agents/trader/artifacts/model-*.json`
- Resultado demo: JSON configurado no CLI.

Métricas mínimas emitidas no estado/log: `decisions_total`, `trades_executed`, `dd_day`, `dd_month`, `cci_f`, `p_win_avg`, `drift_flags`.

## Segurança
- Não usar corretora real nessa versão.
- Não comitar segredos (`.env`, keys, tokens).
