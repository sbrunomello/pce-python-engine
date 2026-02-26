# Glossário de termos da PCE

## AFS (Adaptive Feedback System)
Camada responsável por ajustar parâmetros do modelo interno com base em diferença entre impacto esperado e observado, sem romper continuidade histórica do estado cognitivo.

## AO (Action Orchestrator)
Camada de execução controlada do plano deliberado, incluindo registro de sucesso, impacto e metadados para auditoria.

## CCI (Cognitive Coherence Index)
Métrica proprietária da PCE (0..1) para quantificar coerência cognitiva em tempo real, derivada de consistência decisória, estabilidade de prioridade, não-contradição e precisão preditiva.

## DE (Decision Engine)
Camada de deliberação que seleciona ações com base em estado persistido, aderência a valores (VEL) e coerência corrente (CCI).

## EPL (Event Processing Layer)
Camada de ingestão e validação estrutural de eventos por contratos (JSON Schema), garantindo qualidade semântica mínima da entrada.

## ISI (Internal State Integrator)
Camada que integra eventos ao estado interno, preservando contexto longitudinal e permitindo deliberação não-reativa.

## Responsabilidade estrutural
Princípio segundo o qual decisões devem ser explicáveis por contratos, estado, valores, plano, execução e impacto observável em trilha auditável.

## SM (State Manager)
Camada de persistência de estado e memória de eventos/ações. No estágio atual usa SQLite para portabilidade e simplicidade operacional.

## VEL (Value Evaluation Layer)
Camada que calcula score explícito de aderência do evento/ação a um conjunto de valores estratégicos declarados.

## Violação de valor
Condição detectada quando decisão ou resultado conflita com valor estratégico configurado, elevando taxa de contradição e degradando CCI.
