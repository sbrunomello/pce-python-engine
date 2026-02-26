# ADR 0005 - Estratégia de persistência incremental (SQLite-first)

## Status
Accepted

## Contexto
A PCE requer memória integrada para deliberação persistente. A solução inicial precisa simplicidade operacional, porém com caminho claro para escala.

## Decisão
Adotar estratégia incremental:
1. **Fase inicial:** SQLite local como backend único para estado, memória e snapshots CCI;
2. **Fase intermediária:** particionamento lógico por domínio/agente e políticas de retenção;
3. **Fase avançada:** persistência híbrida (OLTP + armazenamento analítico) mantendo contratos de acesso.

## Consequências
- Entrega rápida de rastreabilidade fim-a-fim.
- Limita throughput concorrente em cenários extremos de escrita.
- Preserva portabilidade de desenvolvimento e reprodutibilidade de testes.

## Alternativas consideradas
- **Banco distribuído desde o início:** rejeitado por custo de operação e complexidade precoce.
- **Sem persistência durável (in-memory):** rejeitado por violar premissas de memória integrada e auditoria.
