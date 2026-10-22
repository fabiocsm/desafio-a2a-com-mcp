# Data Model: Agente A2A para descoberta e reservas diretas

## Modelos públicos A2A v1

Usar Protobuf a2a.types.a2a_pb2 e serialização do SDK. Não misturar modelos Pydantic
legados A2A 0.3 com o wire v1.

| Entidade | Campos / regras |
| --- | --- |
| AgentCard | name, description, version, capabilities, supportedInterfaces, skills e modos texto |
| AgentInterface | url base configurada + /a2a, protocolBinding JSONRPC, protocolVersion 1.0 |
| AgentSkill | id reservar-sala, descrição, tags e exemplos do formato fixo |
| Task | id UUID, context_id UUID, status, history de Message, artifacts |
| TaskStatus | state TASK_STATE_*, message opcional e timestamp UTC se emitido |
| Message | message_id próprio, role ROLE_USER/ROLE_AGENT, parts, task_id/context_id quando associados |
| Part | text, sem campo legado kind |
| Artifact | artifact_id próprio, name reserva, parts com JSON textual da reserva |

O SDK converte snake_case dos modelos para camelCase no JSON e enums para nomes
TASK_STATE_* / ROLE_*. Se houver timestamps do protocolo, emitir UTC com Z.
Os horários de reserva dentro do JSON textual continuam com o offset do domínio.

## Registros internos

| Registro | Campos / validação |
| --- | --- |
| ParsedReservation | sala, inicio, fim, responsavel extraídos por gramática fixa |
| TaskRecord | Task pública e traceparent original opcional; não conter regras de sala |
| HostSnapshot | catálogo de tools descoberto e política/versão lidas explicitamente |
| RequestTrace | valor original por Task; mesmo trace-id em cada request MCP |

Parser esperado: reservar sala=... inicio=... fim=... responsavel=...; os três
primeiros valores são tokens sem espaço, responsavel é o restante do texto.
Malformed input é rejeitado por erro SDK de parâmetro, sem enviar reserva ao MCP.
Sala inexistente, janela e duração continuam sendo avaliadas exclusivamente pelo MCP.

## Estados e identidade

SUBMITTED → WORKING → COMPLETED ou FAILED no caminho desta feature.
004 acrescentará WORKING → INPUT_REQUIRED e retomadas.
Task terminal não retorna a WORKING; GetTask não muda o estado.

Registrar a Task antes de aguardar o HTTP MCP; o await permite GetTask observar
o estado corrente. Não é necessário worker de background ou fila externa.
Nunca reutilizar context_id para criar continuidade entre Tasks distintas.

## Artifact de reserva

JSON em parts[].text com reserva, sala, inicio, fim, responsavel e politica.
Usar a reserva efetivamente devolvida pelo MCP e a versão lida do resource.
O estado de continuação, quando introduzido em 004, ficará fora do objeto público.
