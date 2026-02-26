# Rover Agent (simulador web 2D)

Este agente mantém o **mundo/simulador dentro de `agents/rover`**; o core PCE apenas recebe observações e retorna decisões (adaptadas para ações robóticas).

## Como rodar

```bash
uvicorn api.main:app --reload
```

UI:
- `http://127.0.0.1:8000/agents/rover/`

## Controles

- `POST /agents/rover/control/start`
- `POST /agents/rover/control/stop`
- `POST /agents/rover/control/reset`
- `WS /agents/rover/ws`

## Arquitetura

- `world/`: física grid 2D, sensores, reward e mapas por seed.
- `pce_bridge/`: contratos de evento e bridge para `/events` do PCE.
- `logging/`: logger estruturado e ring buffer para stream de logs na UI.
- `web/`: frontend vanilla (HTML/CSS/JS + canvas).

## Configuração rápida

- Tamanho do mundo e seed estão em `GridWorld(...)` no runtime de `app.py`.
- Para variar seed/tamanho, ajuste os parâmetros da instância em `RoverRuntime`.

## Testes

```bash
pytest -q agents/rover/tests
```
