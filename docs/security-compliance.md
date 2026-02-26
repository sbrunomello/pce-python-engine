# Security & Compliance

Análise de riscos e controles para operação da PCE sob requisitos de rastreabilidade e governança.

## 1) Modelo de risco

### 1.1 Riscos técnicos principais
1. **Entrada malformada ou maliciosa** em eventos.
2. **Deriva silenciosa de comportamento** por adaptação sem observabilidade.
3. **Perda de rastreabilidade** entre decisão e efeito.
4. **Exposição indevida de dados sensíveis** em logs/metadados.

### 1.2 Controles correspondentes
- Contratos explícitos de eventos/ações via JSON Schema.
- Persistência de estado, ação e snapshots de CCI para auditoria.
- Separação de camadas e responsabilidades para análise forense.
- Políticas de desenvolvimento e segurança em `policies/`.

## 2) Validação de contratos

A integridade de entrada é reforçada por contratos em `docs/contracts/`:
- `events.schema.json` define envelope e payload mínimo de eventos.
- `action.schema.json` define estrutura de ações planejadas/executadas.

Benefício de compliance: eventos inválidos são rejeitados no EPL antes de contaminar memória cognitiva.

## 3) Rastreabilidade e auditoria

A trilha de decisão deve ligar:
1. evento recebido;
2. estado carregado e atualizado;
3. score de valores (VEL);
4. plano deliberado (DE);
5. execução e impacto observado (AO);
6. snapshot CCI pós-ação;
7. ajuste adaptativo aplicado (AFS), quando existir.

Esse encadeamento permite reconstrução causal para auditorias internas/externas.

## 4) Recomendações operacionais

- Definir retenção e classificação de dados por criticidade.
- Implementar controle de acesso por papel para leitura de estado/auditoria.
- Integrar assinatura de eventos e trilha imutável em ambientes regulados.
- Monitorar SLOs cognitivos (CCI mínimo, taxa máxima de contradição).

## 5) Limites atuais

- A versão atual prioriza baseline arquitetural e rastreabilidade local.
- Controles criptográficos avançados e trilha imutável distribuída estão previstos para evolução de produção.
