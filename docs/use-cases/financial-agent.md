# Use Case: Agente financeiro empresarial

## Contexto
Gestão contínua de risco e execução estratégica em ambiente com volatilidade dinâmica e exigência de auditoria.

## Evento de entrada (exemplo)

```json
{
  "event_type": "market_signal",
  "source": "risk_feed",
  "payload": {
    "volatility": 0.78,
    "drawdown": 0.19,
    "liquidity": 0.44,
    "exposure": 0.61
  }
}
```

## Deliberação esperada

- **VEL:** reduz score quando risco excede limites estratégicos.
- **DE:** tende a priorizar `stabilize` ou `collect_more_data` quando CCI está sob pressão.
- **AO:** executa com rastreabilidade de rationale e impacto observado.

## Leitura de CCI

- **CCI em alta:** indica estabilidade de prioridade e boa precisão preditiva.
- **CCI em queda:** sinaliza contradições frequentes, possível desalinhamento entre estratégia e execução.

## Exemplo de decisão registrada

```text
action=stabilize
priority=2
rationale="Ação selecionada por score composto ..."
expected_impact=0.58
observed_impact=0.47
```

Interpretação: o gap de impacto reduz precisão preditiva e pode pressionar CCI no próximo ciclo.
