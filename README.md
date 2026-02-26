# pce-python-core

Monorepo Python moderno e leve para a **Persistent Cognition Engine (PCE)**, baseado no whitepaper 2026.

## Visão geral

A PCE implementa cognição persistente com sete camadas desacopladas:

1. **EPL** (`pce/epl`) – ingestão e validação de eventos por JSON Schema
2. **ISI** (`pce/isi`) – integração de eventos em estado interno
3. **VEL** (`pce/vel`) – avaliação contra valores estratégicos explícitos
4. **SM** (`pce/sm`) – persistência de estado e memória de eventos via SQLite
5. **DE** (`pce/de`) – deliberação de ações por estado + VEL + CCI
6. **AO** (`pce/ao`) – orquestração e rastreabilidade de execução
7. **AFS** (`pce/afs`) – adaptação de modelo interno com base em resultados

### CCI (Cognitive Coherence Index)

Métrica normalizada em tempo real (0..1):

`CCI = wc*consistência + ws*estabilidade + wn*(1-taxa_contradições) + wp*precisão_preditiva`

Pesos padrão: `0.35, 0.25, 0.25, 0.15`.

## Estrutura

- `src/pce/` – camadas + core (`cci`, `config`, `types`)
- `api/` – FastAPI mínima (`POST /events`, `GET /cci`)
- `worker/` – loop contínuo de processamento (exemplo)
- `tests/` – testes unitários por camada + integração
- `docs/` – ADRs, arquitetura (Mermaid), contratos e exemplos
- `policies/` – padrões e definição de pronto
- `tools/scripts/` – gates de binários e segredos
- `.github/workflows/ci.yml` – lint, mypy, testes e security gates

## Como rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp config/.env.example .env
pytest -q
ruff check .
mypy src
uvicorn api.main:app --reload
```

## Exemplos funcionais

- Agente financeiro: `docs/contracts/events.example.financial.json`
- Robô autônomo simples: `docs/contracts/events.example.robot.json`

## Próximos passos

- Conector ROS2 para ingestão de eventos robóticos.
- Adaptador Unity VR para telemetria cognitiva.
- Agente pessoal CLI com perfis de valor customizáveis.

## Licença

MIT (`LICENSE`).
