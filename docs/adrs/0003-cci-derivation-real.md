# ADR 0003 - Derivação real do CCI a partir de traços persistidos

## Status
Accepted

## Contexto
A tese PCE 2026 exige que coerência cognitiva seja uma variável operacional verificável, não um indicador subjetivo. Uma métrica abstrata sem vínculo com execução histórica não atende responsabilidade estrutural.

## Decisão
Derivar o CCI exclusivamente de sinais observáveis no `StateManager`:
1. consistência decisória (ações que respeitam valores);
2. estabilidade de prioridade (dispersão de prioridade recente);
3. taxa de contradição (violações explícitas);
4. precisão preditiva (erro entre impacto esperado e observado).

Usar fórmula ponderada normalizada em [0,1] para controle de deliberação em tempo real.

## Consequências
- CCI torna-se auditável e reproduzível.
- Decisão passa a depender de evidência histórica, reduzindo reatividade sem memória.
- Mudanças em pesos exigem governança e benchmark por domínio para evitar regressões de coerência.

## Alternativas consideradas
- **CCI heurístico sem persistência:** rejeitado por baixa rastreabilidade.
- **CCI com pesos dinâmicos automáticos desde o início:** adiado para evitar complexidade prematura sem linha de base estável.
