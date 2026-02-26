# Tutorial end-to-end: deliberação persistente com CCI

Este tutorial conduz um fluxo completo: instalar, executar loop, injetar eventos via API, observar evolução do CCI e interpretar violações de valores.

## 1) Instalar ambiente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## 2) Validar baseline local

```bash
pytest -q
```

Objetivo: confirmar integridade das camadas antes de observar comportamento cognitivo.

## 3) Executar loop de worker

```bash
python -m worker.loop
```

Você verá linhas como:

```text
[00] event=... action=... cci_before=0.650 cci_after=0.672 value=0.700
```

Interpretação:
- `cci_before`: coerência acumulada antes da nova ação;
- `cci_after`: coerência após registrar impacto observado;
- `value`: aderência do evento aos valores explícitos.

## 4) Subir API em outro terminal

```bash
uvicorn api.main:app --reload
```

## 5) Injetar eventos manualmente

### 5.1 Evento com alto alinhamento esperado

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "market_signal",
    "source": "risk_feed",
    "payload": {"volatility": 0.20, "drawdown": 0.05, "liquidity": 0.85}
  }'
```

### 5.2 Evento potencialmente conflitivo

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "market_signal",
    "source": "risk_feed",
    "payload": {"volatility": 0.92, "drawdown": 0.33, "liquidity": 0.10}
  }'
```

## 6) Observar evolução do CCI

```bash
curl http://127.0.0.1:8000/cci
curl http://127.0.0.1:8000/cci/history
```

Analise tendência (subida/queda) e volatilidade temporal do índice.

## 7) Interpretar violações de valores

No pipeline atual, baixo `value_score` pode marcar violação (`long_term_coherence`).

Indicadores práticos:
1. queda de consistência decisória;
2. aumento da taxa de contradição;
3. deterioração de precisão preditiva por diferença entre impacto esperado/observado.

Conclusão operacional: CCI não é apenas diagnóstico; ele influencia deliberação subsequente e fecha o ciclo de responsabilidade estrutural.
