# Contract: Reserva com alternativas e retomada MRTR segura

## Conflito e formulário

Complementa [contrato MCP básico](../../001-servidor-mcp-salas/contracts/mcp.md).
Em reservar_sala ocupado, a resposta deve ser input_required com requestState e
uma única entrada em inputRequests. A entrada contém method elicitation/create,
params.mode form, message e requestedSchema plano com sala string obrigatória.

As alternativas são salas livres no intervalo, capacidade >= solicitada, limitadas
a três e ordenadas por capacidade e id. No estado original, sala-garagem em
2026-11-03 14h–15h oferece sala-fusca e sala-mirante. A chave da pergunta não é
fixada para o cliente.

Sem opção: complete/isError com Sem alternativas disponiveis no intervalo.
Sem form explicitamente declarado: -32021, HTTP 400 e
data.requiredCapabilities = {"elicitation": {"form": {}}}.

## Retomada

O consumidor envia tools/call com:
- id JSON-RPC diferente do original.
- params.name e params.arguments originais.
- params.inputResponses com a chave original e action/content da decisão.
- params.requestState literalmente igual ao token recebido.
- params._meta e headers completos novamente.

Accept só pode confirmar sala originalmente oferecida e ainda livre; servidor
valida o domínio antes de gravar. O resultado completo tem o formato de 001.
Decline e cancel concluem sem isError verdadeiro, com reservado false e motivo.

## Proteção e rejeições

| Condição | Resultado exigido |
| --- | --- |
| Token com alteração de integridade | -32602, sem reserva |
| Token expirado | -32602, sem reserva |
| Argumentos divergentes | -32602 pelo binding do SDK, sem usar valores adulterados |
| Restart, mesma chave/audience, antes da expiração | retomada válida se a opção atende à política |
| Chave ausente/inválida em startup | processo falha com diagnóstico, sem fallback efêmero |
| Escolha fora do schema | não cria reserva; validação conforme SDK/aplicação |

O codec oficial é AES-256-GCM e o prazo é 600 segundos. Não vincular ao id da
chamada, pois o retry deve ter id novo. O servidor não conserva a continuação.

## Exemplos e evidências

Usar os wrappers preservados em exemplos/wire/03, 04, 06 e 11 como referência,
extraindo request.body. Tokens e chaves ilustrativos não são reutilizáveis.
Gerar nova negociação e capturar os valores reais em cada cenário.
