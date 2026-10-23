# Contract: Agente A2A para descoberta e reservas diretas

## Endpoints

| Entrada | Contrato |
| --- | --- |
| GET /.well-known/agent-card.json | HTTP 200, card v1, supportedInterfaces e skill reservar-sala |
| POST /a2a SendMessage | JSON-RPC 2.0, params.message com messageId, role ROLE_USER e parts[].text |
| POST /a2a GetTask | JSON-RPC 2.0, params.id com identidade real da Task |

Porta padrão 7300; card usa a base pública configurada e /a2a. Capabilities não
habilitam streaming, push ou card estendido autenticado; não preencher securitySchemes
de autenticação efetiva. Outros métodos são recusados pelo erro suportado do SDK.

## Perfil de versão

A avaliação usa métodos v1 sem A2A-Version. Neste endpoint dedicado, ausência do
header gera contexto 1.0 por ServerCallContextBuilder. Header explícito é preservado
e validado pelo SDK; versão incompatível é recusada, não convertida.
Essa adaptação é documentada como perfil do starter, diferente do default normativo.
Não manter negociação por sessão nem habilitar compatibilidade automática 0.3.

## SendMessage e GetTask

Pedido: reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>.
Sem taskId, criar Task com id/contextId próprios e histórico da mensagem.
O dispatcher v1 embrulha o retorno de SendMessage em result.task.
GetTask retorna Task diretamente no result na implementação oficial; essa forma
é aceita pelo validador. Não alterar o SDK para reproduzir o wrapper do exemplo 09.

| Resultado MCP | Resultado A2A |
| --- | --- |
| complete, reserva válida e sem isError | Task COMPLETED com artifact reserva |
| complete, isError true | Task FAILED com texto exato da tool visível no histórico |
| input_required | encaminhado cru para integração da 004, sem resposta automática ou falsa conclusão |
| erro técnico/protocolo depois de criar Task | Task FAILED, mensagem `Falha ao executar pedido no servidor MCP`, sem artifact de sucesso, exceção bruta ou corpo MCP privado |

Enviar mensagem para Task COMPLETED/FAILED gera erro antes de chamar MCP.
GetTask de id desconhecido segue o erro TaskNotFound do SDK.
Entrada malformada é rejeitada com erro de parâmetro do SDK antes de criar Task
ou enviar reserva. Falha técnica não pode deixar uma Task já criada indefinidamente
em WORKING. Essas falhas não alteram as mensagens exatas de domínio exigidas.

## Host MCP

Descobrir tools/list antes do primeiro tools/call e ler politica://uso; toda
operação carrega os metadados e headers do contrato MCP. O cliente deve anunciar
`elicitation.form` como objeto em cada request, usar versão fixa moderna e
session.call_tool com allow_input_required=True. Capabilities adicionais do SDK,
como `elicitation.url`, são permitidas. T005/T006/T031 verificam a presença de
form no wire, sem igualdade do objeto inteiro. O callback defensivo nunca responde
a perguntas, e o produto não oferece fluxo de elicitation URL. Não modificar
atributos privados nem reescrever o protocolo.

Capturar traceparent no pedido A2A e passar meta explícita em cada operação MCP
associada à Task; o trace-id não pode mudar. Sem traceparent, não herdar o de outra Task.

A comparação de contratos verifica propriedades obrigatórias e semântica; não
compara nomes/ids ilustrativos, timestamps ou campos opcionais emitidos pelo SDK.
