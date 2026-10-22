# Data Model: Ponte A2A–MRTR com pausa e retomada por Task

## Separação pública e privada

| Registro | Campos |
| --- | --- |
| TaskRecord | public_task: Task Protobuf, traceparent_original: str opcional, pending: PendingContinuation opcional |
| PendingContinuation | tool_name, original_arguments, elicitation_key, ordered_alternatives, pause_text, request_state |
| OriginalArguments | sala, inicio, fim, responsavel exatamente como usados na chamada original |
| ClientDecision | tipo escolha/recusa e sala escolhida opcional |

TaskRecord e PendingContinuation são objetos internos do agente. A API retorna
apenas public_task, nunca o registro completo. PendingContinuation não é incorporada
a metadata da Task nem anexada ao histórico ou aos artifacts.

Não é necessário armazenar o id interno do SDK para reenvio: o agente nunca
reenvia um envelope pronto. A sessão gera id novo e os logs verificam a diferença.
Um id observado para diagnóstico não pode virar dependência de atributo privado.

## Transições

| Estado | Entrada / condição | Próximo estado | Continuação privada |
| --- | --- | --- | --- |
| WORKING | MCP input_required | INPUT_REQUIRED | armazenar |
| INPUT_REQUIRED | GetTask | INPUT_REQUIRED | preservar |
| INPUT_REQUIRED | escolha fora das opções | INPUT_REQUIRED | preservar sem alteração |
| INPUT_REQUIRED | escolha válida ou recusa | WORKING | manter até resultado |
| WORKING após accept | MCP complete/reservado true | COMPLETED | limpar |
| WORKING após decline | MCP complete/reservado false | CANCELED | limpar |
| WORKING | isError da tool | FAILED | limpar |
| WORKING após retry | erro de protocolo/rede/estado expirado | FAILED | limpar |
| COMPLETED/CANCELED/FAILED | SendMessage | rejeição, estado mantido | não recriar |

GetTask não modifica o registro. Registrar a decisão do cliente e o resultado no
histórico público sem copiar estruturas MCP com token. Estados intermediários
ficam disponíveis ao GetTask enquanto o agente aguarda HTTP.

## Regras de isolamento e apresentação

- A chave única de busca do registro é taskId; contextId não substitui a identidade.
- ordered_alternatives vem de enum ou de uma opção const, sem reordenação.
- pause_text = prefixo literal alternativas: seguido de ids unidos por vírgula e espaço.
- Escolha inválida usa o mesmo pause_text e não chama MCP.
- request_state é devolvido literalmente; a criptografia não é conhecida pelo agente.
- traceparent_original pertence à Task e é passado explicitamente ao host em cada chamada.
- Reinício do agente perde registros transitórios; reinício do MCP não exige perder
  os registros do agente nem renovar token ou segredo.
