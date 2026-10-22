# Contract: Ponte A2A–MRTR com pausa e retomada por Task

## Pedido ocupado e pausa pública

Um SendMessage no formato original abre Task e chega ao MCP real por HTTP.
Ao receber input_required, o agente devolve Task com:
- id/contextId originais.
- status.state TASK_STATE_INPUT_REQUIRED.
- mensagem de texto exatamente alternativas: <ids separados por virgula e espaco>.
- histórico público sem requestState.

Com o estado inicial do starter e pedido sala-garagem em 2026-11-03 14h–15h:
alternativas: sala-fusca, sala-mirante.
Não copiar a lista de uma captura que já tinha outras reservas.

## Continuação

SendMessage usa params.message.taskId da Task existente e texto escolha=<id>
ou escolha=recusar. O agente mantém identidade; não abre outra Task.

| Decisão | Request MCP | Resultado A2A |
| --- | --- | --- |
| sala fora de enum/const | nenhum | mesma pausa e lista |
| sala oferecida | novo tools/call, accept/content.sala | COMPLETED se a reserva concluir |
| recusar | novo tools/call, action decline | CANCELED após complete sem reserva |
| Task terminal | nenhum | erro SDK e estado preservado |

O retry contém params.name e params.arguments originais, inputResponses com a chave
real da pergunta e requestState literal. Header/meta completos em cada request.
O id é novo, atribuído pela sessão SDK. O campo arguments.sala continua sendo a
sala pedida originalmente, não a alternativa.

## Falhas e dados privados

isError da tool: FAILED com texto exato no histórico.
Falha de protocolo/rede na retomada: FAILED sem artifact de sucesso e com mensagem
técnica que não contém requestState ou segredo. Nunca abrir token para resolver falha.

Todas as respostas A2A, inclusive GetTask, card, erros e artifacts, devem excluir
requestState e o registro PendingContinuation. Comparar respostas com todos os
tokens emitidos no cenário, não apenas com uma chave ou prefixo específico.

## Rastreamento e múltiplas Tasks

O trace-id recebido no pedido inicial é preservado nos requests MCP da Task,
inclusive quando a continuação não envia novo header. Um header posterior não
substitui o trace-id original por outro de uma Task diferente.
As duas Tasks do teste de isolamento usam intervalos distintos e podem escolher
a mesma sala livre em cada intervalo, sem misturar suas reservas.

Os contratos de transporte e tipos permanecem os de
[A2A](../../003-agente-a2a-reservas/contracts/a2a.md) e
[MRTR](../../002-reserva-mrtr-segura/contracts/mrtr.md).
