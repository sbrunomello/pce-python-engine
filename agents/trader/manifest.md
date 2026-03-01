# Manifesto Trader PCE v1.1 (Implementação v0 Demo)

## Escopo
- Execução: 1h.
- Filtro macro: 4h.
- Universo default: BTC, ETH, SOL (configurável).
- Predição: Triple-Barrier, horizonte 6h (`TP_FIRST`, `SL_FIRST`, `NONE`).
- Janela alvo de treino: rolling 18 meses (v0 aceita dataset disponível).
- Retraining semanal e drift check diário.
- Threshold inicial: `p_win >= 0.60`.

## Guardrails
- Risco por trade: 0,5% do equity (demo).
- DD diário: 2%.
- DD mensal: 10%.
- Máx. trades por dia: 8 global, 3 por ativo.

## CCI-F / Modos
- `>= 0.85`: normal
- `0.70 - 0.85`: cauteloso
- `0.55 - 0.70`: restrito
- `< 0.55`: travado
- Hard rule: integridade de dados ruim trava entradas.

## Contrato LLM
- LLM é camada de expressão (headline + bullets + risco + gatilhos).
- LLM **não decide trade** e **não altera TradePlan**.

## Operação v0
- Market data real (Binance público) para demo live.
- Portfólio e execução via `MockBroker` determinístico.
- Sem integração com corretora real.
- Sem integração com `pce-os` nesta entrega.
