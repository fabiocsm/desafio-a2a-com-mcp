# Data Model: Reserva com alternativas e retomada MRTR segura

## Payload interno e estado externo

| Campo do payload | Tipo / regra |
| --- | --- |
| schema_version | inteiro fixo 1, validado ao reconstruir |
| tool_name | reservar_sala |
| original_arguments | sala, inicio, fim, responsavel originais |
| alternatives | lista ordenada de até três ids oferecidos |
| elicitation_key | identificador atribuído pelo servidor, criado ao emitir a pergunta |
| politica | versão extraída da política original |

O payload é serializado pelo handler e entregue ao SDK, que devolve ao consumidor
um token requestState protegido. O consumidor só guarda esse token; não precisa
conhecer o payload. Não guardar a continuação em dicionário ou sessão no MCP.

## Claims fornecidas pelo SDK

RequestStateBoundary acrescenta versão do envelope, emissão/expiração, audience,
método, alvo e digest dos argumentos e aplica o codec AES-256-GCM. TTL = 600s.
O nome/audience e a chave precisam permanecer estáveis após restart.
No caminho de entrada, a fronteira valida e abre o estado antes do handler;
ctx.request_state contém o payload, não um token para descriptografar novamente.

## Pergunta e resposta

- InputRequest: chave variável do servidor; método elicitation/create; mode form;
  schema plano com sala string obrigatória, enum ordenado ou const com uma opção.
- InputResponse: mesma chave; action accept com content.sala, ou decline/cancel.
- Continuação: requestState e inputResponses obrigatoriamente juntos; mapa de
  respostas com exatamente a elicitation_key selada. Campo incompleto, mapa vazio,
  chave divergente ou entrada adicional resulta em -32602 sem mutação.
- O retry mantém original_arguments; a sala escolhida viaja somente no content
  da resposta. Isso preserva o digest usado pelo SDK.

## Transições e mutações

| Estado observado no MCP | Evento | Resultado / mutação |
| --- | --- | --- |
| Pedido livre válido | chamada inicial | complete, nova reserva |
| Conflito com opções e capability | chamada inicial | input_required, nenhuma reserva |
| Conflito sem opção | chamada inicial | complete/isError, nenhuma reserva |
| Estado válido e accept válido | retry | revalidar opção e criar reserva |
| Opção oferecida ocupada após emissão | retry accept | complete/isError: true, sem nova pergunta e sem gravação; texto não normatizado |
| Estado válido e decline/cancel | retry | complete, reservado false, motivo; sem gravação |
| Estado inválido/expirado ou argumentos divergentes | retry | -32602 antes da tool; sem gravação |
| Continuação incompleta, correlação inválida ou payload incompatível | retry | -32602 na validação SDK/handler, antes de qualquer mutação |

Estados acima descrevem requests independentes, não uma máquina de sessão guardada
pelo servidor. A validade do token pode sobreviver ao processo; as reservas transitórias não.
