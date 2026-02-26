# Use Case: Agente robótico autônomo

## Contexto
Navegação autônoma e execução de missão com restrições simultâneas de segurança, estabilidade e progresso.

## Evento de entrada (exemplo)

```json
{
  "event_type": "robot_telemetry",
  "source": "onboard_sensor_fusion",
  "payload": {
    "obstacle_distance_m": 0.42,
    "battery": 0.36,
    "surface_slip": 0.31,
    "mission_progress": 0.57
  }
}
```

## Deliberação esperada

- Em cenário de risco físico elevado, **VEL** penaliza ações de agressividade operacional.
- **DE** pode favorecer `stabilize` com prioridade alta para preservar segurança.
- **AO** registra impacto observado (ex.: redução de risco vs atraso de missão).

## CCI na operação robótica

- **Consistência decisória:** proporção de ações alinhadas a valores de segurança.
- **Estabilidade:** variação de prioridade entre ciclos de controle.
- **Não-contradição:** incidência de violações de valor (ex.: segurança sacrificada sem justificativa).
- **Precisão preditiva:** aderência entre impacto esperado e telemetria pós-ação.

## Exemplo de ciclo

```text
event=robot_telemetry
action=stabilize
cci_before=0.63
cci_after=0.66
value=0.71
```

Interpretação: aumento de CCI sugere melhora de coerência sistêmica após execução conservadora.
