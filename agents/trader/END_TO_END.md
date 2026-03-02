# Agent Trader — Guia de subida e teste ponta a ponta (E2E)

Este guia descreve um fluxo **reprodutível**, do zero, para:

1. preparar ambiente local;
2. subir o Agent Trader;
3. rodar testes automatizados;
4. validar o pipeline E2E via CLI (dataset → treino → replay → live-demo → inspeção de ledger/UI);
5. executar checks de troubleshooting.

> Escopo: `agents/trader` (demo local, sem corretora real).

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

## 4.3 Treinar modelo (walk-forward supervisionado)

```bash
python agents/trader/cli.py train --dataset agents/trader/artifacts/dataset_e2e.csv
```

### Comportamento esperado com dataset pequeno

Com poucos exemplos, o treino pode retornar:

- `"trained": false`
- `"reason": "insufficient_samples"`

Isso **não é erro de execução**; é proteção de qualidade do pipeline.

## 4.4 Ativar modelo (somente se houve treino com sucesso)

Liste os modelos gerados em artifacts e selecione uma versão:

```bash
ls -1 agents/trader/artifacts/model-*.json
```

Ative a versão desejada:

```bash
python agents/trader/cli.py model activate --version model-YYYYMMDDHHMMSS
```

> Se não houver modelo treinado, pule esta etapa e siga para replay/live-demo.

## 4.5 Replay com candles históricos (execução determinística)

```bash
python agents/trader/cli.py replay --csv agents/trader/data/sample_candles.csv
```

Valide no JSON de saída:
- lista `decisions` preenchida;
- `decision_event_id` e `execution_event_id` por decisão;
- campos de governança (`feature_version`, `label_version`, `policy_version`, `value_policy_version`).

## 4.6 Live demo (ciclo único com mercado atual)

```bash
python agents/trader/cli.py live-demo --output agents/trader/artifacts/live_demo_e2e.json
```

Validações:
- arquivo de saída foi criado;
- comando encerra com sucesso;
- `decisions` pode ser `0` dependendo das condições de mercado/filtros.

## 4.7 Inspecionar ledger para auditoria

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

## 5) Subir e validar a UI local

Suba o servidor local:

```bash
python agents/trader/cli.py ui --host 127.0.0.1 --port 8787 --loop-interval 2
```

Acesse no navegador:

- `http://127.0.0.1:8787`

Checks recomendados:
- página responde e renderiza;
- estado é exibido;
- start/stop do loop de controle funciona;
- eventos em tempo real chegam via websocket.

---

## 6) Checklist de validação E2E (rápido)

- [ ] `pytest agents/trader/tests -q` verde.
- [ ] `dataset build` gera arquivo + hash.
- [ ] `train` executa e responde coerentemente (`trained=true` ou `insufficient_samples`).
- [ ] `replay` retorna decisões com cadeia causal.
- [ ] `live-demo` cria output JSON.
- [ ] `ledger tail/query` retornam eventos recentes.
- [ ] UI sobe e responde localmente.

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
```
