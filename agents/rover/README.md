# Rover Agent (simulador web 2D)

Este agente mantém o **mundo/simulador dentro de `agents/rover`**; o core PCE recebe observações e retorna **ações robóticas explícitas**.

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
- `POST /agents/rover/control/reset_stats` (zera contadores de tentativas/sucessos/falhas)
- `POST /agents/rover/control/clear_policy` (zera Q-table + hiperparâmetros)
- `WS /agents/rover/ws`

## Episódios, energia e razões de término

- O rover inicia cada episódio com `battery_max=200.0`.
- Custos de energia por ação:
  - `robot.move_forward`: `1.0 * amount`
  - `robot.turn_left`: `0.5`
  - `robot.turn_right`: `0.5`
  - `robot.stop`: `0.2`
- A energia é sempre limitada a `>= 0.0`.
- Se a energia chega em `0.0` antes do goal, o episódio termina com `reason="battery_depleted"`.
- O runtime reinicia automaticamente o mundo quando `done=true`, mantendo a execução contínua.

Reward shaping adicional:
- mantém baseline por passo (`-0.1`), bônus de goal (`+100`) e penalidade de colisão (`-5`);
- adiciona penalidade terminal de bateria (`-50`) quando `reason="battery_depleted"`.

## Aprendizado RL (Q-learning tabular)

- **Estado discreto**: `d{dir}_dx{sign(dx)}_dy{sign(dy)}_f{bucket(front)}_l{bucket(left)}_r{bucket(right)}`.
- **Ações**: `FWD`, `L`, `R`, `S` mapeadas para `robot.move_forward`, `robot.turn_left`, `robot.turn_right`, `robot.stop`.
- **Política**: epsilon-greedy com persistência no SQLite (`robotics_q_values`, `robotics_params`).
- **Atualização real**: `Q(s,a) ← Q(s,a) + α * (r + γ * max_a' Q(s',a') - Q(s,a))` no evento de feedback.

### Hiperparâmetros padrão

- `alpha=0.2`
- `gamma=0.95`
- `epsilon=1.0`
- `epsilon_decay=0.9995`
- `epsilon_min=0.05`

## Observabilidade

A UI exibe:
- epsilon atual;
- modo da política (`explore`/`exploit`);
- melhor ação do estado;
- reward médio em janela.
- energia atual (battery);
- tentativas totais, sucessos e falhas por motivo (`battery_depleted`, `timeout`, `collision`);
- taxa de sucesso;
- cronômetro da execução (inicia em `Start` e só para ao atingir goal).

O grid também marca o ponto de partida do episódio em laranja.

Além disso, o backend gera log estruturado `q_update` a cada atualização RL.

## Arquitetura

- `world/`: física grid 2D, sensores, reward e mapas por seed.
- `pce_bridge/`: contratos de evento e bridge para `/events` do PCE.
- `logging/`: logger estruturado e ring buffer para stream de logs na UI.
- `web/`: frontend vanilla (HTML/CSS/JS + canvas).

## Configuração rápida

- Tamanho do mundo, seed, alcance e ruído de sensores estão em `GridWorld(...)` no runtime de `app.py`.
- Performance do runtime: `tick_rate_hz` (simulação), `frame_rate_hz` (render), `feedback_every` e `log_every` em `RoverRuntime`.
- URL do PCE pode ser sobrescrita via `PCE_EVENTS_URL` (default: `http://127.0.0.1:8000/events`).

## Testes

```bash
pytest -q agents/rover/tests tests/test_robotics_rl.py
```
