# Implementation Plan: Ponte A2A–MRTR com pausa e retomada por Task

**Branch**: `dev` (branch Git real, preservado) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-ponte-a2a-mrtr/spec.md`

**Feature context**: `004-ponte-a2a-mrtr` é o contexto retornado pelo setup; não é um branch Git criado.

## Summary

Adicionar ao agente uma continuação privada por taskId que transforma o InputRequiredResult cru do MCP em pausa A2A e retoma o pedido com a decisão do cliente. O SDK MCP mantém o wire e atribui novo id a cada chamada; o agente guarda apenas os parâmetros originais e o token opaco.

Abrange FR-001 a FR-016 da spec 004, integrando 002 e 003 sem alterar o domínio MCP. As Tasks públicas usam somente modelos A2A; a continuação privada nunca entra em campos serializáveis da Task.

Dependências: 002-reserva-mrtr-segura e 003-agente-a2a-reservas, sobre a base 001.

Phase 0 consolidada em [research.md](research.md); Phase 1 detalhada em
[data-model.md](data-model.md), [contrato](contracts/ponte.md) e
[quickstart.md](quickstart.md). Este plano encerra o design; não cria código nem tasks.md.

## Technical Context

**Language/Version**: Python 3.12+ como baseline do projeto; o requisito mínimo externo é Python 3.10+.

**Primary Dependencies**: Sem novos pacotes: mcp==2.3.0 e a2a-sdk[http-server]==1.2.3, mantendo os pins HTTP/Pydantic comuns de 003. Usar apenas a sessão MCP de baixo nível com allow_input_required=True.

**Storage**: TaskRecord em memória com Task pública, traceparent original e PendingContinuation privada opcional; limpar continuação nos estados terminais. Nenhum token em metadata/history/artifact.

**Testing**: unittest/IsolatedAsyncioTestCase e unittest.mock da biblioteca padrão; HTTP real e subprocessos para integração; validador original na aceitação final.

**Target Platform**: Execução local em macOS/Linux, loopback HTTP, um worker por processo; sem container ou deploy.

**Project Type**: Dois serviços HTTP independentes, servidor MCP e agente A2A, sem interface gráfica.

**Performance Goals**: Não há SLA de latência ou throughput no enunciado. Chamadas terminam com resultado ou pausa, sem aguardar decisão humana; escala de cinco salas.

**Constraints**: MCP v2/2026-07-28, A2A v1.0, dois processos, sem LLM, sem sessão de protocolo, arquivos protegidos imutáveis e erros/textos exatos.

**Scale/Scope**: Duas ou mais Tasks independentes, uma pergunta por Task, respostas sem streaming e sem persistência após restart do agente.

### Decisões compartilhadas

Preservar o perfil A2A e a variante de capability documentados na 003. Guardar somente parâmetros MCP originais (nome/argumentos), nunca um envelope JSON-RPC completo para reenvio. A nova chamada da sessão recebe id próprio do SDK, e a chave da elicitation vem sempre da resposta recebida.

## Constitution Check

Gate de entrada: requisitos e restrições constitucionais revisados antes das decisões
específicas. Gate de saída: design revisto após research, modelos e contratos.
A aprovação abaixo é de design; não declara que testes da aplicação passaram.

| Princípio | Antes de Phase 0 | Após Phase 1 / evidência de design |
| --- | --- | --- |
| I. Fronteiras e responsabilidade | PASS — requisito preservado | PASS — Agente traduz pergunta/decisão; servidor continua responsável por alternativas e reserva. |
| II. Estado explícito | PASS — requisito preservado | PASS — TaskId seleciona a continuação; MCP recebe novo request com estado ecoado e sem sessão. |
| III. Integridade/opacidade | PASS — requisito preservado | PASS — Token armazenado literalmente em estrutura privada e nunca aberto no agente. |
| IV. Contratos/determinismo | PASS — requisito preservado | PASS — Lista exata de alternativas, enum/const, recusa e terminalidade preservados. |
| V. Conformidade/rastreio | PASS — requisito preservado | PASS — Dois fluxos intercalados, logs dos ids e trace por Task, teste amplo de vazamento. |

Gate de saída verifica que nenhuma estrutura contendo PendingContinuation é passada aos serializers A2A. Não gravar o token em Task.metadata, mesmo que pareça conveniente. A checagem de escolha pelo enum/const não é regra de domínio: apenas respeita o formulário recebido. A conclusão só ocorre após o resultado real do MCP; a recusa não é um cancelamento exclusivamente local.

## Project Structure

### Documentation (this feature)

```text
specs/004-ponte-a2a-mrtr/
├── spec.md
├── specify-input.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/ponte.md
└── checklists/requirements.md
```

### Source Code (repository root)

Estrutura proposta para implementação; estes arquivos de aplicação não são criados
pelo planejamento. Dados, exemplos e validador permanecem nas posições originais.

```text
agente/
├── src/ponte_agente/
│   ├── handler.py      # continua a mesma Task, sem nova identidade
│   ├── mcp_host.py     # chamada inicial e retry raw com meta por chamada
│   ├── tasks.py        # registro público/privado e terminalidade
│   └── ponte.py        # pergunta, validação da escolha e tradução de resultado
└── tests/
    └── test_ponte.py
servidor-mcp/            # permanece outro processo HTTP, sem importação
```

**Structure Decision**: Adicionar um módulo de tradução e ampliar o registro de Task existente. Sem grafo de agentes, fila externa, workflow engine, serviço de sessões ou armazenamento de tokens no modelo público.

### Sequência de implementação a detalhar em tasks.md

1. Introduzir PendingContinuation com nome/argumentos originais, chave da pergunta, alternativas ordenadas, texto exato da pausa e token opaco; o trace original permanece no TaskRecord.
2. Interpretar somente o formato esperado de InputRequiredResult: uma elicitation form e sala restrita por enum ou const. Montar a lista a partir do schema sem consultar domínio no agente.
3. Persistir o estado privado antes de publicar INPUT_REQUIRED e devolver o controle A2A; registrar mensagem da pergunta no histórico público sem incluir o objeto MCP.
4. Na continuação, localizar taskId e recusar estados terminais antes de qualquer chamada MCP. Para escolha inválida, conservar estado/token/pergunta e repetir o texto byte a byte.
5. Para escolha válida, montar input_responses com a chave original e accept/content.sala. Repetir session.call_tool com nome/argumentos originais, request_state literal e meta de trace original; deixar o SDK gerar id novo.
6. Para recusa, enviar decline pelo mesmo mecanismo e somente então finalizar CANCELED se o MCP retornar complete sem reserva; nunca fabricar cancelamento sem consumir a continuação no servidor.
7. Aplicar resultados à mesma Task: COMPLETED/artifact em sucesso, FAILED com texto original para isError, FAILED com diagnóstico técnico sem dados privados para erro JSON-RPC/HTTP na retomada.
8. Limpar PendingContinuation após qualquer estado terminal; manter histórico e artifact públicos consultáveis. Preservar trace-id ao retomar sem header novo, sem utilizar o trace de outra Task.
9. Testar dois fluxos pausados e retomados em ordem inversa, determinismo de perguntas, enum/const, invalid choice, todos os terminais, callback nunca invocado e busca de vazamento além do teste oficial.

### Validação e rastreabilidade

FR-001/002/003/004/005: pausa real, formato e privacidade; FR-006/007/008: escolha, params e ids novos; FR-009/010/011/012: efeitos reais, recusa, falha e terminais; FR-013/014/015/016: isolamento, determinismo, trace e integração HTTP. As verificações oficiais 27–34 e 36 cobrem parte da ponte; o teste local deve ampliar a checagem de vazamento para todos os tokens/Tasks, não apenas o prefixo de um token conhecido.

### Cobertura por requisito

Os casos abaixo são validações planejadas, não resultados de testes já executados.

| Requisito da spec | Evidência prevista |
| --- | --- |
| FR-001 | Pausa real e retorno do controle ao cliente. |
| FR-002 | Linha exata e ordem extraída de enum/const. |
| FR-003 | Pedido/pergunta/token privados associados ao taskId. |
| FR-004 | Busca de todos os tokens em todas as respostas públicas. |
| FR-005 | GetTask mostra a mesma pausa e identidade. |
| FR-006 | Escolha inválida repete pergunta sem chamar MCP. |
| FR-007 | Retry usa novo id SDK, parâmetros originais e token literal. |
| FR-008 | Escolha vai em content; servidor decide a reserva. |
| FR-009 | Mesma Task COMPLETED e artifact correto. |
| FR-010 | Decline real no MCP antes de Task CANCELED. |
| FR-011 | Erro da tool e erro técnico terminam FAILED sem falsa confirmação. |
| FR-012 | Os três terminais recusam continuação antes de MCP. |
| FR-013 | Duas Tasks concluídas em ordem inversa sem troca de dados. |
| FR-014 | Pedidos iguais sem mutação geram pausas byte a byte iguais. |
| FR-015 | Retry sem header novo preserva trace-id original. |
| FR-016 | Integração real preserva descoberta, política, metadata e headers. |

### Riscos e limites

Objetos Protobuf serializam metadata e campos adicionados ao público: manter as estruturas separadas por construção. Erros de rede podem conter detalhes de request; apresentar diagnóstico técnico sem token. O id MCP deve ser provado pelos logs, sem acessar contador/atributo privado do SDK. Não interpretar ids das salas para recalcular alternativas. Reinício do agente pode perder Tasks; o requisito de restart é do MCP.

## Complexity Tracking

Sem violações constitucionais ou exceções de complexidade. As adaptações de perfil
necessárias ao wire do starter estão documentadas em research.md e no contrato;
não alteram SDKs, arquivos protegidos ou as regras do desafio. Não há camada de
serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
