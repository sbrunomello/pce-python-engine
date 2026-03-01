# Trader Agent (PCE) - Demo v0 (Sprint 3: Deliberação governada por valores)

Agente independente em `agents/trader`, sem integração com `pce-os`, usando somente `pce-core` (StateManager).

## Objetivo
Pipeline completa em camadas PCE:
- EPL: ingestão/validação de candles 1h/4h.
- ISI: integração de estado + features técnicas.
- VEL: scoring de oportunidade/risco/qualidade.
- SM: persistência em SQLite via `pce-core` StateManager.
- DE: deliberação com alternativas explícitas (`ENTER_LONG`, `EXIT_LONG`, `HOLD`, `REDUCE`, `NO_TRADE`) e seleção por score de valor.
- AO: execução mock (`MockBroker`) com BUY/SELL, fee/slippage determinísticos e PnL realizado/não realizado.
- AFS: labels Triple-Barrier robustas (HIGH/LOW + ATR), treino supervisionado leve, walk-forward multi-split e drift.
- Event Ledger append-only para auditoria/replay determinístico.

## Fluxo Sprint 2 (end-to-end)
1) **Build dataset from candles** (pipeline real EPL -> ISI -> features):
```bash
python agents/trader/cli.py dataset build --candles-csv agents/trader/data/sample_candles.csv --out agents/trader/artifacts/dataset.csv --symbols BTCUSDT,ETHUSDT --timeframe 1h
```

2) **Treinar com walk-forward**:
```bash
python agents/trader/cli.py train --dataset agents/trader/artifacts/dataset.csv
```
(compatível com legado: `--csv`).

3) **Ativar modelo aprovado**:
```bash
python agents/trader/cli.py model activate --version model-YYYYMMDDHHMMSS
```

4) **Executar replay/live-demo**:
```bash
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv
python agents/trader/cli.py live-demo --output agents/trader/artifacts/live_demo.json
```

5) **Drift altera policy automaticamente**:
- em drift, trader sobe threshold, reduz risco e troca `policy_version`.
- em drift, trader também versiona `value_policy_version` e registra `value_policy.updated`.
- se houver baseline aprovado anterior, pode ocorrer rollback para modelo anterior.

## Sprint 3 - Governança por valores

### Value model versionado
- Estado agora persiste `value_policy` completo (pesos, thresholds, modificadores por modo e `value_policy_version`).
- Toda decisão carrega `value_policy_version` no `TradePlan`.
- Toda mutação automática de política de valor gera nova versão e evento `value_policy.updated`.

### Deliberação com alternativas
- O Decision Engine sempre gera e ordena 5 alternativas explícitas.
- Cada alternativa possui:
  - `expected_value`
  - `risk`
  - `cost`
  - `quality`
  - `consistency`
  - `final_score`
  - `rationale`
- A melhor alternativa válida é escolhida de forma determinística.

### TradePlan completo
- `TradePlan` inclui:
  - `entry_price`, `stop_price`, `take_price`
  - `risk_R`, `expected_R`
  - `invalidation_reason`, `time_horizon`
  - `value_breakdown`
  - `alternatives` (lista completa de `TradeOption`)
- `stop_price` é baseado em ATR e `take_price` em múltiplo fixo de R.

### CCI-F real (DC/RS/VR/PA)
- Componentes:
  - **DC**: coerência de decisão com política/threshold.
  - **RS**: estabilidade de exposição vs limite operacional.
  - **VR**: taxa de violações de policy em janela recente.
  - **PA**: alinhamento com acerto direcional recente.
- Persistência no estado:
  - `metrics.cci_f`, `metrics.dc`, `metrics.rs`, `metrics.vr`, `metrics.pa`.
- Atualização observável por `metrics.ccif.updated`.

### Governança forte
- `VR` alto gera `policy.violation.alert`.
- `PA` muito baixo gera `learning.performance.alert`.
- `CCI-F` determina modo automaticamente (`normal`, `cautious`, `restricted`, `locked`).
- Com modo `locked`, entradas novas são bloqueadas até recuperação.

## Versionamento e reprodutibilidade
Toda decisão e treino são governados por versões:
- `feature_version`: versão do conjunto de features geradas no ISI.
- `label_version`: versão do labeling triple-barrier.
- `model_version`: versão do artefato treinado.
- `policy_version`: versão da política operacional (threshold/risk/mode).
- `dataset_hash`: hash determinístico do dataset gerado.

## Eventos observáveis no ledger
- `learning.train.run.started`
- `learning.train.run.completed`
- `learning.model.promoted`
- `learning.model.rolled_back`
- `learning.drift.detected`
- `policy.updated`
- `value_policy.updated`
- `decision.options.evaluated`
- `metrics.ccif.updated`
- `policy.violation.alert`
- `learning.performance.alert`

## Event Envelope padrão
Todos os eventos emitidos pelo trader seguem `EventEnvelope` com:
- `event_id`, `event_type`, `ts`, `source`, `payload`
- `correlation_id`, `causation_id`, `actor`, `version`

Cadeia causal obrigatória:
- candle -> decision (`decision.causation_id = candle.event_id`)
- decision -> execution (`execution.causation_id = decision.event_id`)

## Persistência e artifacts
- Estado persistido: `agents/trader/artifacts/trader_state.db`
- Ledger de eventos: `agents/trader/artifacts/ledger/events.jsonl`
- Logs estruturados de decisões: `agents/trader/artifacts/logs/decisions.jsonl`
- Modelos: `agents/trader/artifacts/model-*.json`
- Datasets: caminho escolhido em `dataset build` (CSV local; sem commit de datasets grandes)

## Limitações
- Ainda é demo: **sem corretora real**.
- LLM segue como camada de expressão (explicabilidade), não decide trade.

## Testes
```bash
pytest agents/trader/tests -q
```
