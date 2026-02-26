# ADR 0004 - Ajuste adaptativo de valores com guardrails

## Status
Accepted

## Contexto
Sistemas estratégicos autônomos operam em ambientes não estacionários. Valores explícitos precisam adaptação controlada para manter utilidade sem perder governança.

## Decisão
Permitir ajuste adaptativo de parâmetros internos relacionados a valores por meio do AFS, com guardrails:
1. preservar trilha auditável de mudanças;
2. nunca sobrescrever definição base de valores sem revisão humana;
3. limitar taxa de ajuste por janela temporal;
4. monitorar impacto em CCI antes/depois de cada ajuste.

## Consequências
- Aumenta robustez frente a drift ambiental.
- Mantém separação entre **valor normativo** (estável) e **parâmetro operacional** (adaptável).
- Introduz necessidade de observabilidade mais rica para explicar variações de coerência.

## Alternativas consideradas
- **Valores totalmente estáticos:** rejeitado por baixa adaptação contextual.
- **Autoajuste irrestrito:** rejeitado por risco de desalinhamento silencioso e fragilidade de compliance.
