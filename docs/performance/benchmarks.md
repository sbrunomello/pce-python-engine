# Benchmarks iniciais de desempenho

Documento de referência para medições preliminares da implementação SQLite-first.

## 1) Metodologia simplificada

- Ambiente local de desenvolvimento.
- Carga sequencial de eventos homogêneos.
- Medição por estágio lógico do pipeline.

> Observação: números abaixo são orientativos para baseline de engenharia e não substituem benchmark de produção.

## 2) Latência por camada (estimativa inicial)

| Camada | Função principal | Latência típica (ms) |
|---|---|---:|
| EPL | validação/normalização | 0.3 - 1.2 |
| ISI | integração de estado | 0.2 - 0.8 |
| VEL | scoring de valores | 0.1 - 0.6 |
| SM (read/write) | persistência SQLite | 1.0 - 6.5 |
| DE | deliberação | 0.2 - 1.0 |
| AO | execução simulada + registro | 0.4 - 2.0 |
| AFS | adaptação de modelo | 0.2 - 0.9 |

Latência fim-a-fim observada em carga leve: **~3 ms a 12 ms por evento**.

## 3) Escalabilidade inicial e limites SQLite

### Pontos fortes
- Setup mínimo, alta portabilidade, previsibilidade em ambiente single-node.
- Excelente para prototipagem e validação de contratos cognitivos.

### Limites conhecidos
1. **Concorrência de escrita:** lock de banco em cenários de múltiplos writers.
2. **Crescimento de histórico:** consultas em tabelas de ação/CCI exigem índices e retenção.
3. **Throughput sustentado:** degrada sob ingestão burst sem batching.

### Mitigações recomendadas
- Habilitar WAL e políticas de checkpoint.
- Criar retenção temporal de snapshots CCI.
- Evoluir para arquitetura híbrida na Fase 2/3 do roadmap.
