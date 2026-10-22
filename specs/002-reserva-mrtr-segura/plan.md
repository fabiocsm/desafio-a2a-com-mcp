# Implementation Plan: Reserva com alternativas e retomada MRTR segura

**Branch**: `dev` (branch Git real, preservado) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-reserva-mrtr-segura/spec.md`

**Feature context**: `002-reserva-mrtr-segura` é o contexto retornado pelo setup; não é um branch Git criado.

## Summary

Completar reservar_sala usando MRTR manual do MCPServer 2.3.0. A tool devolve InputRequiredResult e o SDK aplica RequestStateSecurity com AES-256-GCM, chave estável do ambiente e TTL de 600 segundos. A retomada recupera o pedido do payload verificado, sem mapa de negociações no servidor.

Abrange FR-001 a FR-014 da spec 002. O agente e a associação a Tasks não pertencem a esta feature; o contrato é validado com consumidor MCP direto.

Dependências: 001-servidor-mcp-salas; mantém seus schemas, erros, domínio e transporte.

Phase 0 consolidada em [research.md](research.md); Phase 1 detalhada em
[data-model.md](data-model.md), [contrato](contracts/mrtr.md) e
[quickstart.md](quickstart.md). A decomposição executável está em [tasks.md](tasks.md);
os artefatos documentais não implementam a aplicação.

## Technical Context

**Language/Version**: Python 3.12+ como baseline do projeto; o requisito mínimo externo é Python 3.10+.

**Primary Dependencies**: Mesmos pins de 001: mcp==2.3.0, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3, pydantic==2.12.0. Segurança fornecida pelo próprio SDK, sem implementação criptográfica própria.

**Storage**: Reservas em memória como em 001; nenhuma continuação em memória no MCP. Payload da operação fica exclusivamente no requestState protegido que o consumidor guarda.

**Testing**: unittest/IsolatedAsyncioTestCase e unittest.mock da biblioteca padrão; HTTP real e subprocessos para integração; validador original na aceitação final.

**Target Platform**: Execução local em macOS/Linux, loopback HTTP, um worker por processo; sem container ou deploy.

**Project Type**: Dois serviços HTTP independentes, servidor MCP e agente A2A, sem interface gráfica.

**Performance Goals**: Não há SLA de latência ou throughput no enunciado. Chamadas terminam com resultado ou pausa, sem aguardar decisão humana; escala de cinco salas.

**Constraints**: MCP v2/2026-07-28, A2A v1.0, dois processos, sem LLM, sem sessão de protocolo, arquivos protegidos imutáveis e erros/textos exatos.

**Scale/Scope**: Uma pergunta por conflito, no máximo três alternativas e TTL fixo de 600 segundos; suporte a restart do servidor com a mesma chave.

### Decisões compartilhadas

Manter nome MCPServer/audience estável `ponte-salas`. Configurar RequestStateSecurity(keys=[secret_bytes], ttl=600), com bytes.fromhex de REQUEST_STATE_SECRET. Rejeitar segredo ausente, hex inválido ou menos de 32 bytes em startup; não gerar chave efêmera de fallback. MRTR manual permite a aplicação transferir a decisão ao cliente sem bloquear nem usar callback.

## Constitution Check

Gate de entrada: requisitos e restrições constitucionais revisados antes das decisões
específicas. Gate de saída: design revisto após research, modelos e contratos.
A aprovação abaixo é de design; não declara que testes da aplicação passaram.

| Princípio | Antes de Phase 0 | Após Phase 1 / evidência de design |
| --- | --- | --- |
| I. Fronteiras e responsabilidade | PASS — requisito preservado | PASS — Alternativas e decisão de criar reserva permanecem em ponte_mcp. |
| II. Estado explícito | PASS — requisito preservado | PASS — Payload autocontido no estado transportado; novo request para retry, sem memória de continuação. |
| III. Integridade/opacidade | PASS — requisito preservado | PASS — AES-256-GCM do SDK, TTL 600, segredo estável e binding de método/nome/argumentos. |
| IV. Contratos/determinismo | PASS — requisito preservado | PASS — Form explícito, enum/const, ordenação e recusa com semântica exata. |
| V. Conformidade/rastreio | PASS — requisito preservado | PASS — Testes HTTP/subprocesso demonstram rejeições e restart; registros preservam método/id/trace. |

O SDK protege e abre requestState antes do handler. O handler deve usar ctx.request_state já verificado, sem outro codec. A checagem automática -32021 foi confirmada no helper Resolve/Elicit, não no InputRequiredResult manual; portanto a tool deve conferir estritamente ctx.client_capabilities.elicitation.form e lançar MCPError oficial com requiredCapabilities. Não aceitar elicitation genérica como substituta do form mode.

## Project Structure

### Documentation (this feature)

```text
specs/002-reserva-mrtr-segura/
├── spec.md
├── specify-input.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
├── contracts/mrtr.md
└── checklists/requirements.md
```

### Source Code (repository root)

Estrutura proposta para implementação; estes arquivos de aplicação não são criados
pelo planejamento. Dados, exemplos e validador permanecem nas posições originais.

```text
servidor-mcp/
├── pyproject.toml
├── src/ponte_mcp/
│   ├── app.py          # RequestStateSecurity, nome/audience estável
│   ├── entrada.py      # preservado da 001
│   ├── modelos.py      # payload MRTR versionado e resultados
│   ├── salas.py        # alternativas e reserva da opção validada
│   └── mrtr.py         # pergunta, capability e retomada via contexto SDK
└── tests/
    ├── test_salas.py   # existente da 001, acrescentar matriz de alternativas
    └── test_mrtr.py    # HTTP, adulteração, relógio e subprocesso/restart
```

**Structure Decision**: Adicionar somente o módulo MRTR e o modelo do payload ao servidor existente. A proteção criptográfica e os erros de estado continuam nas fronteiras oficiais do SDK; não criar store de negociações, endpoint de sessão ou serviço de criptografia próprio.

### Sequência executável em tasks.md

1. Verificar os gates da implementação 001 e preparar consumidor HTTP direto; nenhuma aplicação foi implementada por este planejamento.
2. Na fundação, adicionar payload versionado autocontido e configurar RequestStateSecurity(keys=[secret_bytes], ttl=600), com nome ponte-salas estável e sem fallback ephemeral. A proteção deve estar ativa antes da primeira emissão.
3. Na US1, filtrar salas livres com capacidade suficiente, ordenar por (capacidade, id) e limitar a três; sem opções, devolver complete/isError com a mensagem exata.
4. Montar InputRequiredResult com uma ElicitRequest form e payload serializado, após conferir form no request atual; o SDK aplica claims, AES-GCM e expiração. Não aguardar callback.
5. No retry, distinguir chamada inicial de continuação pela presença dos campos: ambos ausentes indicam inicial; presença de qualquer um exige requestState e inputResponses válidos. Rejeitar -32602 antes de mutação se faltar um, se o mapa estiver vazio ou se suas chaves não forem exatamente a elicitation_key selada. Ler ctx.request_state já verificado e ctx.input_responses; accept seleciona uma opção oferecida e revalida disponibilidade antes de gravar.
6. Na US2, exercitar a matriz de segurança da spec com erros nativos do SDK para integridade, expiração e argumentos divergentes; validar payload e correlação no handler com tipos de erro públicos quando necessário. Não converter erros de protocolo em isError de domínio; demonstrar restart real sem store de continuação.
7. Na US3, concluir a matriz negativa form ausente/genérico/url-only, opção única e decline/cancel sem gravação e sem isError verdadeiro.
8. Executar regressão/reprodução e registrar evidências. As dependências por tarefa e os três grupos possíveis de paralelismo estão em tasks.md.

### Validação e rastreabilidade

FR-001/002/003/004/005: matriz de alternativas e capability; FR-006/007/008: chave, TTL, payload e restart real; FR-009/010/011: novo id no consumidor, envelopes e adulteração; FR-012/013: resultado de aceite/recusa e efeitos nas reservas; FR-014: fronteira sem A2A. Os testes locais correspondem às verificações oficiais 13–20 e acrescentam expiração, cancel e restart ausentes da suíte automática.

### Cobertura por requisito

Os casos abaixo são validações planejadas, não resultados de testes já executados.

| Requisito da spec | Evidência prevista |
| --- | --- |
| FR-001 | Ordenação, capacidade e limite de três alternativas. |
| FR-002 | Uma pergunta, input_required, estado e ausência de gravação. |
| FR-003 | Form schema plano, enum/const e campo sala obrigatório. |
| FR-004 | Conflito sem opção devolve mensagem exata. |
| FR-005 | Form ausente/genérico/url-only rejeitados com -32021/400. |
| FR-006 | AES-GCM oficial, payload e expiração de 600 segundos. |
| FR-007 | Secret hexadecimal de >=32 bytes, obrigatório no ambiente. |
| FR-008 | Teste real de restart MCP sem store de continuação. |
| FR-009 | Consumidor usa id novo e campos params; continuação incompleta ou chave divergente é rejeitada sem mutação. |
| FR-010 | Integridade e expiração rejeitadas antes de reservar. |
| FR-011 | Digest de argumentos rejeita adulteração. |
| FR-012 | Accept preserva pedido, confirma opção ainda livre e rejeita ocupação posterior com complete/isError sem nova negociação. |
| FR-013 | Decline/cancel completam sem erro e sem gravação. |
| FR-014 | Nenhuma associação a Task ou interpretação do token pelo cliente. |

### Riscos e limites

Trocar a chave ou o nome/audience entre emissão e retry invalida o estado; manter ambos constantes. TTL não deve ser renovado ao reiniciar. Um estado criptografado ainda deve ser opaco para o agente. A indisponibilidade surgida depois da oferta deve terminar em complete/isError: true, sem nova pergunta e sem gravação. O texto desse erro adicional não é fixado pelo desafio; não substituir nenhuma das mensagens obrigatórias para as condições já normatizadas. A matriz de aceite da spec e T008/T009/T013 tornam o caso verificável sem exigir mensagem artificialmente exata.

## Complexity Tracking

Sem violações constitucionais ou exceções de complexidade. As adaptações de perfil
necessárias ao wire do starter estão documentadas em research.md e no contrato;
não alteram SDKs, arquivos protegidos ou as regras do desafio. Não há camada de
serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
