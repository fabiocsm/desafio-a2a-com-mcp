# Contract: Servidor MCP de salas e reservas diretas

## Transporte e envelope

POST /mcp, porta padrão 7301; Streamable HTTP com respostas JSON, sem canal SSE
mantido aberto e sem sessão de protocolo. O SDK oficial é responsável pelo wire.

Cada request carrega params._meta com:
- io.modelcontextprotocol/protocolVersion: "2026-07-28".
- io.modelcontextprotocol/clientCapabilities: objeto presente, inclusive vazio quando não houver elicitation.
- traceparent: opcional, registrado quando fornecido.

Headers: Content-Type: application/json; Accept pode declarar application/json e
text/event-stream conforme os exemplos; MCP-Protocol-Version espelha a versão,
Mcp-Method o método, Mcp-Name o nome da tool/URI quando aplicável.
Aceitar o header de transporte não habilita streaming no produto.

| Operação | Entrada | Saída completa |
| --- | --- | --- |
| tools/list | sem argumentos de domínio | três tools com inputSchema de objeto; listar_salas com outputSchema |
| tools/call listar_salas | arguments: {} | structuredContent.salas e JSON equivalente em content[].text |
| tools/call consultar_disponibilidade | sala, inicio, fim obrigatórios | sala, livre, conflitos; JSON estruturado e texto equivalente |
| tools/call reservar_sala | sala, inicio, fim, responsavel obrigatórios | reserva, reservado: true, sala, inicio, fim, responsavel, politica |
| resources/read politica://uso | uri | contents com uri, mimeType text/markdown e texto original |

Os nomes em Python podem ser snake_case; no wire o SDK deve serializar resultType,
structuredContent, inputSchema e outputSchema com a grafia do contrato.

## Intervalos e validação compartilhada

Início e fim exigem timezone explícito. Converter os instantes para -03:00 antes
de conferir a janela 08:00–20:00 no mesmo dia local, com fim posterior ao início e
duração de até duas horas. Offsets equivalentes representam os mesmos instantes;
atravessar a noite viola a janela. Intervalos adjacentes não se sobrepõem e datas
passadas são permitidas. Formatos inválidos seguem a rejeição do schema/SDK, sem
nova mensagem de domínio. Com formatos válidos e múltiplas violações, consulta e
reserva aplicam a precedência sala, intervalo, janela, duração, conforme FR-006,
FR-009 e data-model.md.

## Categorias de erro

| Condição | Resposta |
| --- | --- |
| Metadata obrigatória ausente, inclusive sem header moderno | JSON-RPC error -32602, HTTP 400; não completar metadata |
| Header divergente do corpo | JSON-RPC error -32020 pelo SDK |
| Tool inexistente | -32602 ou complete/isError, conforme SDK |
| URI inexistente | -32602, nunca contents vazio |
| Sala desconhecida | complete/isError: true; Sala inexistente: <id informado> |
| Janela inválida | complete/isError: true; Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00 |
| Duração excessiva | complete/isError: true; Duracao acima do limite: a politica permite no maximo 2 horas |
| Intervalo vazio/invertido | complete/isError: true; Intervalo invalido: fim deve ser posterior a inicio |

Prefixos do SDK são permitidos, mas o trecho exato de domínio deve aparecer.
A guarda de presença usa modelos/erros do SDK e termina antes das tools; não é
um segundo dispatcher MCP. Requests válidos são repassados sem modificar o corpo.

## Observabilidade e evolução

Registrar cada entrada em stderr com método, id e _meta.traceparent quando presente,
antes de possíveis rejeições. Não registrar corpo integral ou estado privado.
O contrato de reserva ocupada será completado por [MRTR](../../002-reserva-mrtr-segura/contracts/mrtr.md).

Referências de wire preservadas: ../../../exemplos/wire/01-tools-list.json,
02-tools-call-livre.json e 05-resources-read-politica.json na mesma pasta.
