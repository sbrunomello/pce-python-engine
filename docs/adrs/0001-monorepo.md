# ADR 0001 - Monorepo modular para PCE

## Status
Accepted

## Contexto
A arquitetura PCE exige sete camadas desacopladas, contratos explícitos, persistência e auditabilidade.

## Decisão
Adotar um monorepo Python único (`pce-python-core`) com pacotes independentes por camada em `src/pce/*`.

## Consequências
- Facilita teste de integração entre camadas sem acoplamento de implementação.
- Permite evoluções futuras (ROS2, Unity VR, agente pessoal CLI) por interfaces estáveis.
