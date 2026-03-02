# Agent Trader — Guia ponta a ponta (E2E) atualizado para o novo front

Este guia descreve um fluxo **reprodutível**, do zero, para:

1. preparar ambiente local;
2. subir o Agent Trader;
3. rodar testes automatizados;
4. validar o pipeline E2E via CLI (dataset → treino → replay → live-demo → inspeção de ledger/UI);
5. operar o novo front **PCE Observability Console** (abas, trace e controles);
6. gerar corretamente o CSV histórico esperado pelo replay.

> Escopo: `agents/trader` (demo local, sem corretora real).
>
> Compatível com a UI atual (`ui_version=0.3.5`) servida por `agents/trader/ui_server.py`.

---

## 1) Pré-requisitos

- Python 3.12+.
- `pip` atualizado.
- Ambiente virtual Python (fortemente recomendado).
- Dependências do projeto instaladas a partir de `agents/trader/pyproject.toml`.

### 1.1 Criar e ativar ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 1.2 Instalar dependências do Trader

```bash
python -m pip install -e agents/trader
```

> Se você já roda testes do repositório completo, mantenha as dependências globais sincronizadas para evitar variações locais.

---

## 2) Estrutura de artefatos e limpeza inicial

O Trader grava estado e evidências em `agents/trader/artifacts`.

Arquivos relevantes:
- `agents/trader/artifacts/trader_state.db` (SQLite de estado);
- `agents/trader/artifacts/ledger/events.jsonl` (event ledger append-only);
- `agents/trader/artifacts/logs/decisions.jsonl` (decisões estruturadas);
- `agents/trader/artifacts/model-*.json` (modelos treinados);
- datasets gerados por você (`dataset build`).

### 2.1 Reset opcional para execução determinística de teste

```bash
rm -f agents/trader/artifacts/trader_state.db
rm -f agents/trader/artifacts/ledger/events.jsonl
rm -f agents/trader/artifacts/logs/decisions.jsonl
rm -f agents/trader/artifacts/model-*.json
```

> Use o reset apenas em ambiente de desenvolvimento local.

---

## 3) Testes automatizados (sanidade antes do E2E)

Execute os testes do Agent Trader:

```bash
pytest agents/trader/tests -q
```

Critério esperado: suíte verde.

---

## 4) Pipeline E2E via CLI

A ordem abaixo cobre o fluxo de ponta a ponta e facilita auditoria posterior no ledger.

## 4.1 Descobrir comandos disponíveis

```bash
python agents/trader/cli.py --help
```

Comandos principais: `dataset`, `train`, `model`, `replay`, `live-demo`, `ledger`, `ui`.

## 4.2 Gerar dataset a partir de candles (EPL → ISI → features)

```bash
python agents/trader/cli.py dataset build \
  --candles-csv agents/trader/data/sample_candles.csv \
  --out agents/trader/artifacts/dataset_e2e.csv \
  --symbols BTCUSDT,ETHUSDT \
  --timeframe 1h
```

Validações rápidas:
- arquivo de saída existe;
- retorno JSON contém `feature_version` e `dataset_hash`.

## 4.3 Como gerar o CSV histórico esperado para replay

O replay (`python agents/trader/cli.py replay --csv ...`) e o modo replay da API (`POST /api/control/start`) esperam **candles OHLCV** com este cabeçalho exato:

```csv
symbol,timeframe,timestamp,open,high,low,close,volume
```

Regras importantes:
- `symbol`: string (ex.: `BTCUSDT`), sem espaços.
- `timeframe`: string (ex.: `1h`, `4h`).
- `timestamp`: ISO-8601 parseável por `datetime.fromisoformat` (ex.: `2025-01-01T00:00:00+00:00`).
- `open,high,low,close,volume`: números decimais válidos.

### 4.3.1 Opção rápida (arquivo de exemplo pronto)

Use o dataset de candles já versionado no repositório:

```bash
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv
```

### 4.3.2 Gerar CSV histórico via Binance (script curto)

Se quiser montar seu próprio histórico, use o script abaixo (gera candles de 1h, UTC):

```bash
python - <<'PY'
import csv
from datetime import datetime, UTC
from pathlib import Path

import httpx

symbol = "BTCUSDT"
interval = "1h"
limit = 500
out = Path("agents/trader/artifacts/candles_btcusdt_1h.csv")
url = "https://api.binance.com/api/v3/klines"

resp = httpx.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=30)
resp.raise_for_status()
rows = resp.json()

out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"])
    for k in rows:
        ts = datetime.fromtimestamp(k[0] / 1000, tz=UTC).isoformat()
        w.writerow([symbol, interval, ts, k[1], k[2], k[3], k[4], k[5]])

print(out)
PY
```

Depois execute:

```bash
python agents/trader/cli.py replay --csv agents/trader/artifacts/candles_btcusdt_1h.csv
```

## 4.4 Treinar modelo (walk-forward supervisionado)

```bash
python agents/trader/cli.py train --dataset agents/trader/artifacts/dataset_e2e.csv
```

### Comportamento esperado com dataset pequeno

Com poucos exemplos, o treino pode retornar:

- `"trained": false`
- `"reason": "insufficient_samples"`

Isso **não é erro de execução**; é proteção de qualidade do pipeline.

## 4.5 Ativar modelo (somente se houve treino com sucesso)

Liste os modelos gerados em artifacts e selecione uma versão:

```bash
ls -1 agents/trader/artifacts/model-*.json
```

Ative a versão desejada:

```bash
python agents/trader/cli.py model activate --version model-YYYYMMDDHHMMSS
```

> Se não houver modelo treinado, pule esta etapa e siga para replay/live-demo.

## 4.6 Replay com candles históricos (execução determinística)

```bash
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv
```

Valide no JSON de saída:
- lista `decisions` preenchida;
- `decision_event_id` e `execution_event_id` por decisão;
- campos de governança (`feature_version`, `label_version`, `policy_version`, `value_policy_version`).

## 4.7 Live demo (ciclo único com mercado atual)

```bash
python agents/trader/cli.py live-demo --output agents/trader/artifacts/live_demo_e2e.json
```

Validações:
- arquivo de saída foi criado;
- comando encerra com sucesso;
- `decisions` pode ser `0` dependendo das condições de mercado/filtros.

## 4.8 Inspecionar ledger para auditoria

Últimos eventos:

```bash
python agents/trader/cli.py ledger tail --limit 20
```

Consulta por tipo:

```bash
python agents/trader/cli.py ledger query --type decision.options.evaluated --limit 10
```

Consulta por símbolo:

```bash
python agents/trader/cli.py ledger query --symbol BTCUSDT --limit 10
```

---

## 5) Subir e validar a UI local (novo front)

Suba o servidor local:

```bash
python agents/trader/cli.py ui --host 127.0.0.1 --port 8787 --loop-interval 2
```

Acesse no navegador:

- `http://127.0.0.1:8787`

Checks recomendados:
- página responde e renderiza;
- status no topo mostra `running`, `mode`, `cci_f`, `equity`, `locked`;
- controles globais funcionam (`Start`, `Stop`, `Pause`, `Resume`, `Reset`);
- abas renderizam corretamente (`Overview`, `Live Event Stream`, `Trace Explorer`, `Decisions`, `Portfolio & Execution`, `Models & Learning`, `Policies & Values`, `System / Debug`);
- eventos em tempo real chegam via websocket (`/ws/events`).

### 5.1 Fluxo recomendado no novo front

1. **Overview**: validar saúde geral e versões ativas.
2. **Live Event Stream**: monitorar eventos recentes e filtrar por `event_type`, `symbol`, `correlation_id`.
3. **Decisions**: abrir trace direto por linha de decisão (`Open Trace`).
4. **Trace Explorer**: confirmar cadeia causal e duração por estágio (EPL→ISI→VEL→SM→DE→AO→AFS).
5. **Portfolio & Execution**: conferir posições mock e eventos `execution.order.filled`.
6. **Policies & Values**: ajustar policy/value policy de forma controlada.
7. **System / Debug**: inspecionar snapshot bruto e exportar ledger (`/api/download/ledger_tail`).

### 5.2 Replay usando API (quando quiser alimentar histórico na UI)

O botão **Start** da UI inicia em modo `live`. Para replay histórico (com CSV), use a API:

```bash
curl -X POST http://127.0.0.1:8787/api/control/start \
  -H 'content-type: application/json' \
  -d '{"mode":"replay","replay_csv":"agents/trader/artifacts/candles_btcusdt_1h.csv","interval_sec":0.2}'
```

Se o `replay_csv` não for informado em modo replay, a API retorna erro `400`.

---

## 6) Checklist de validação E2E (rápido)

- [ ] `pytest agents/trader/tests -q` verde.
- [ ] `dataset build` gera arquivo + hash.
- [ ] `train` executa e responde coerentemente (`trained=true` ou `insufficient_samples`).
- [ ] `replay` retorna decisões com cadeia causal.
- [ ] `live-demo` cria output JSON.
- [ ] `ledger tail/query` retornam eventos recentes.
- [ ] UI sobe e responde localmente (abas + websocket + trace).

---

## 7) Troubleshooting

### 7.1 `train` sempre retorna `insufficient_samples`

- Gere dataset maior (mais candles/símbolos/timeframes).
- Verifique se o CSV de candles tem colunas esperadas e dados sem lacunas críticas.

### 7.2 `live-demo` sem decisões

- Pode ocorrer por guardrails/mode restritivo no momento.
- Verifique estado/policy e decisões no ledger.

### 7.3 UI não sobe na porta

- Porta ocupada: altere `--port`.
- Confirme dependências web instaladas no ambiente ativo.

### 7.4 Ledger vazio

- Execute `replay` para popular eventos;
- confira permissões de escrita em `agents/trader/artifacts`.

### 7.5 Erro de replay por CSV inválido

Sintomas comuns:
- erro de parsing de `timestamp`;
- colunas ausentes (`symbol,timeframe,timestamp,open,high,low,close,volume`);
- valores não numéricos em OHLCV.

Correções:
- normalize o timestamp para ISO-8601 com timezone (`+00:00`);
- garanta cabeçalho exato e ordem consistente;
- valide `float(...)` em `open/high/low/close/volume` antes do replay.

---

## 8) Comandos de referência (copiar e colar)

```bash
# 1) Testes
pytest agents/trader/tests -q

# 2) Dataset
python agents/trader/cli.py dataset build \
  --candles-csv agents/trader/data/sample_candles.csv \
  --out agents/trader/artifacts/dataset_e2e.csv \
  --symbols BTCUSDT,ETHUSDT \
  --timeframe 1h

# 3) Treino
python agents/trader/cli.py train --dataset agents/trader/artifacts/dataset_e2e.csv

# 4) Replay
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv

# 5) Live demo
python agents/trader/cli.py live-demo --output agents/trader/artifacts/live_demo_e2e.json

# 6) Ledger
python agents/trader/cli.py ledger tail --limit 20
python agents/trader/cli.py ledger query --type decision.options.evaluated --limit 10

# 7) UI
python agents/trader/cli.py ui --host 127.0.0.1 --port 8787 --loop-interval 2

# 8) Replay na UI via API (CSV histórico)
curl -X POST http://127.0.0.1:8787/api/control/start \
  -H 'content-type: application/json' \
  -d '{"mode":"replay","replay_csv":"agents/trader/data/sample_candles.csv","interval_sec":0.2}'
```
