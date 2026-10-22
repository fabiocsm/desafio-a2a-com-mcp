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
[quickstart.md](quickstart.md). Este plano encerra o design; não cria código nem tasks.md.

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
    └── test_mrtr.py    # HTTP, adulteração, relógio e subprocesso/restart
```

**Structure Decision**: Adicionar somente o módulo MRTR e o modelo do payload ao servidor existente. A proteção criptográfica e os erros de estado continuam nas fronteiras oficiais do SDK; não criar store de negociações, endpoint de sessão ou serviço de criptografia próprio.

### Sequência de implementação a detalhar em tasks.md

1. Adicionar payload versionado com pedido original completo, alternativas ordenadas, chave da pergunta e versão da política, sem qualquer referência a um objeto em memória.
2. Filtrar salas livres com capacidade suficiente usando a mesma lógica de disponibilidade; ordenar por (capacidade, id) e limitar a três.
3. Quando houver conflito sem opções, devolver complete/isError com a mensagem exata. Havendo opções, verificar elicitation.form do request atual antes de emitir a pergunta.
4. Montar InputRequiredResult com uma entrada ElicitRequest em mode form e request_state contendo o payload serializado. Deixar RequestStateBoundary aplicar as claims, AES-GCM e expiração.
5. Configurar RequestStateSecurity(keys=[secret_bytes], ttl=600) no MCPServer e manter o nome do servidor constante entre reinícios; não usar o default ephemeral.
6. No retry, ler ctx.input_responses e ctx.request_state; recuperar a chave e o pedido original do payload verificado. Accept seleciona somente uma alternativa oferecida; decline/cancel não grava reserva.
7. Usar a rejeição nativa do SDK para argumentos divergentes e estado adulterado/expirado; não converter esses casos em isError de domínio.
8. Testar form ausente/genérico/url-only, enum/const, limite/ordem, ausência de alternativas, aceite/recusa, adulteração, expiração e restart em subprocesso com a mesma chave.

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
| FR-009 | Consumidor usa id novo e campos params da retomada. |
| FR-010 | Integridade e expiração rejeitadas antes de reservar. |
| FR-011 | Digest de argumentos rejeita adulteração. |
| FR-012 | Accept preserva pedido e confirma a opção oferecida. |
| FR-013 | Decline/cancel completam sem erro e sem gravação. |
| FR-014 | Nenhuma associação a Task ou interpretação do token pelo cliente. |

### Riscos e limites

Trocar a chave ou o nome/audience entre emissão e retry invalida o estado; manter ambos constantes. TTL não deve ser renovado ao reiniciar. Um estado criptografado ainda deve ser opaco para o agente. A indisponibilidade surgida depois da oferta não pode produzir reserva sobreposta: revalidar a alternativa no commit; como o enunciado não fixa a mensagem desse caso, reutilizar erro de domínio aplicável sem inventar fluxo de negociação adicional.

## Complexity Tracking

Sem violações constitucionais ou exceções de complexidade. As adaptações de perfil
necessárias ao wire do starter estão documentadas em research.md e no contrato;
não alteram SDKs, arquivos protegidos ou as regras do desafio. Não há camada de
serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
