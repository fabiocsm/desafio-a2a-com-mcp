# Feature Specification: Agente A2A para descoberta e reservas diretas

**Feature Branch**: `dev` (ramo atual; nenhum ramo criado)

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Permitir descobrir o agente, enviar pedidos fixos de reserva e consultar Tasks com resultados e falhas vindos do servidor MCP." — [entrada completa para $speckit-specify](specify-input.md)

**Feature Directory**: `specs/003-agente-a2a-reservas`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Descobrir o serviço e confirmar uma reserva livre (Priority: P1)

Como assistente da empresa, quero descobrir o agente de salas e enviar um pedido de reserva para receber uma confirmação verificável.

**Why this priority**: Disponibiliza ao mundo a capacidade já existente no servidor de salas.

**Independent Test**: Com agente e servidor reais iniciados, consultar o card, enviar reserva de sala-porao em 2026-11-03 das 09:00 às 10:00 (-03:00) para Doc e verificar o resultado.

**Acceptance Scenarios**:

1. **Given** o agente iniciado na configuração padrão, **When** um cliente busca /.well-known/agent-card.json, **Then** recebe HTTP 200 com identidade, capabilities e interface JSON-RPC de versão 1.0 em /a2a e a skill reservar-sala
2. **Given** sala-porao livre no intervalo pedido, **When** o cliente envia SendMessage sem taskId no formato fixo, **Then** uma nova Task com id e contextId próprios passa por SUBMITTED e WORKING e termina COMPLETED
3. **Given** a reserva concluída, **When** o cliente examina o artifact reserva, **Then** encontra JSON em parte de texto com identificação da reserva, sala, início, fim, responsável e politica obtida do resource

---

### User Story 2 - Acompanhar resultados e falhas da Task (Priority: P1)

Como cliente, quero consultar uma Task e entender falhas sem perder sua identidade ou reabrir uma operação já encerrada.

**Why this priority**: Identidade, estado e produto são o contrato externo da capacidade do agente.

**Independent Test**: Consultar Tasks concluídas e com falha, verificar o histórico e enviar nova mensagem a uma Task terminal.

**Acceptance Scenarios**:

1. **Given** uma Task existente, **When** o cliente chama GetTask com seu id, **Then** recebe o mesmo id e contextId, estado corrente e artifacts quando existirem
2. **Given** um pedido para sala-delorean inexistente, **When** o agente recebe isError da ferramenta de reserva, **Then** a Task termina TASK_STATE_FAILED com Sala inexistente: sala-delorean visível no histórico
3. **Given** uma Task COMPLETED ou FAILED, **When** o cliente envia SendMessage referenciando-a, **Then** recebe erro, sem reabrir a Task nem executar nova reserva

---

### User Story 3 - Consumir capacidades descobertas e rastrear o pedido (Priority: P2)

Como responsável pela integração, quero comprovar que o agente usa o serviço de salas e mantém a identificação do pedido entre os dois processos.

**Why this priority**: Demonstra a integração real e permite localizar problemas sem duplicar regras de sala.

**Independent Test**: Inspecionar registros do servidor durante um pedido com traceparent, verificando descoberta anterior à chamada de reserva, leitura da política e metadados enviados.

**Acceptance Scenarios**:

1. **Given** o agente ainda sem descoberta de ferramentas, **When** chega o primeiro pedido, **Then** tools/list ocorre antes do primeiro tools/call e o catálogo descoberto orienta as chamadas
2. **Given** um traceparent fornecido pelo cliente, **When** o agente envia requests MCP associados à Task, **Then** todos levam o mesmo trace-id em _meta, além de versão, capabilities e headers coerentes
3. **Given** a política fornecida pelo servidor, **When** o agente confirma a reserva, **Then** a versão no artifact corresponde à primeira linha do resource, sem versão copiada de constante local

### Edge Cases

- Erros de política devolvidos pela tool também devem gerar Task FAILED com o texto original, sem o agente recalcular regras.
- Uma Task sem artifact disponível ainda deve manter identidade e estado consultáveis.
- A ausência de traceparent na entrada não exige inventar um trace-id, nem autoriza reutilizar o de outra Task.
- Reutilizar o cliente MCP não autoriza omitir metadados nas próximas chamadas.
- Um input_required não é sucesso nem erro de domínio: seu tratamento completo é responsabilidade da spec 004, sem callback que escolha pelo cliente.
- O agente não deve criar horários alternativos, trocar sala ou interpretar linguagem natural.

### Validação automatizada dos cenários

Automatizar os cenários de aceite com testes de contrato e integração entre os
dois processos HTTP reais, além de testes de parser e transições de Task. Cobrir
card, reserva livre, GetTask durante execução e após conclusão/falha, mensagens
exatas de domínio, terminalidade, descoberta, origem da política, metadados/headers
em cada request e isolamento do trace entre Tasks. Fixtures controladas podem
variar a política sem editar os arquivos protegidos. Testar o retorno MCP
input_required cru e ausência de callback automático, reservando a pausa/retomada
A2A para 004. Esses testes verificam requisitos existentes e não substituem o
validador integral nem os critérios manuais da entrega.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O agente DEVE ser processo separado do MCP e consumir suas capacidades por HTTP, sem importar funções de domínio e sem duplicar regras de sala.
- **FR-002**: O GET /.well-known/agent-card.json DEVE responder 200 com Agent Card A2A v1.0 contendo identidade, capabilities, supportedInterfaces com URL /a2a, protocolBinding JSONRPC, protocolVersion 1.0 e skill de id reservar-sala, conforme o exemplo 07.
- **FR-003**: O endpoint /a2a na porta padrão 7300 DEVE aceitar SendMessage e GetTask no binding JSON-RPC 2.0 sobre HTTP, com configuração de porta opcional preservando o padrão.
- **FR-004**: SendMessage sem taskId DEVE criar Task com id e contextId próprios e registrar seu trânsito por TASK_STATE_SUBMITTED e TASK_STATE_WORKING antes de terminar.
- **FR-005**: O agente DEVE interpretar o formato `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>` por regras determinísticas, sem LLM ou SDK de provedor de LLM nos manifestos.
- **FR-006**: Antes da primeira chamada de tool, o agente DEVE executar tools/list e usar as definições descobertas, sem um catálogo fixo de ferramentas no código.
- **FR-007**: O agente DEVE ler politica://uso e extrair da primeira linha a versão a incluir no artifact; sua origem DEVE ser a leitura explícita do resource, nunca uma constante local. Reutilizar o conteúdo lido durante a execução é permitido.
- **FR-008**: Cada request MCP DEVE incluir em _meta io.modelcontextprotocol/protocolVersion, io.modelcontextprotocol/clientCapabilities com elicitation em form mode na forma `{"elicitation": {"form": {}}}`, sem inferir capabilities por sessão.
- **FR-009**: O agente DEVE enviar headers coerentes com o corpo: MCP-Protocol-Version, Mcp-Method e Mcp-Name em tools/call e resources/read.
- **FR-010**: Se o cliente enviar traceparent no header A2A, todos os requests MCP associados à Task DEVEM carregar o mesmo trace-id no traceparent de _meta, permitindo novo span-id sem substituir o trace-id.
- **FR-011**: Sucesso da reserva DEVE concluir a Task em TASK_STATE_COMPLETED com artifact de name reserva, contendo em parte de texto o JSON com reserva, sala, inicio, fim, responsavel e politica conforme o contrato.
- **FR-012**: Resultado isError: true da tool DEVE concluir a Task em TASK_STATE_FAILED e preservar a mensagem exata da tool no histórico, incluindo a sala inexistente.
- **FR-013**: GetTask DEVE devolver id, contextId, estado corrente e artifacts existentes sem alterar a Task.
- **FR-014**: Tasks COMPLETED e FAILED NÃO DEVEM voltar a WORKING; SendMessage dirigido a elas DEVE gerar erro sem nova chamada de reserva. A mesma regra para CANCELED é completada na spec 004.
- **FR-015**: O agente NÃO DEVE expor requestState em suas respostas nem responder automaticamente à elicitation. A pausa e retomada completas são o escopo da spec 004, sem contrato provisório que as substitua.

### Key Entities *(include if feature involves data)*

- **Agent Card**: Identidade pública, interface, versão e skill descobertas por outros agentes.
- **Task**: Pedido identificado por id e contextId, com estado, histórico e artifacts.
- **Pedido de reserva**: Sala, início, fim e responsável extraídos do texto fixo do cliente.
- **Artifact de reserva**: Produto verificável da Task, incluindo a versão da política lida do servidor.
- **Contexto de rastreamento**: Trace-id associado à Task e propagado entre os processos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um cliente descobre a capacidade de reserva e conclui um pedido válido de sala livre sem conhecer as regras internas do serviço.
- **SC-002**: 100% das confirmações incluem os campos exigidos da reserva, incluindo a versão correta da política; nenhuma exige interpretação de linguagem natural.
- **SC-003**: Em todos os cenários de consulta, o cliente recupera a identidade original e o estado corrente de sua operação.
- **SC-004**: Todos os erros de execução recebidos do serviço de salas ficam visíveis ao cliente com sua mensagem original, sem confirmação indevida.
- **SC-005**: Pedidos encerrados não são reabertos e 100% dos pedidos de aceite com identificação de rastreamento mantêm a mesma identificação entre os serviços.

## Assumptions

- Depende de [001 — Servidor MCP](../001-servidor-mcp-salas/spec.md); reserva em conflito depende de [002](../002-reserva-mrtr-segura/spec.md) e da ponte [004](../004-ponte-a2a-mrtr/spec.md).
- A ordem recomendada de desenvolvimento é 001, 002, 003, 004, 005; esta feature é validável com pedidos sem conflito mesmo antes da ponte.
- Todos os cinco princípios se aplicam, com ênfase na separação de responsabilidades, descoberta real e rastreabilidade.
- Tasks podem ficar em memória; não há exigência de recuperá-las após reinício do agente.
- Entradas seguem o formato fechado do desafio; interface gráfica, linguagem natural, streaming, autenticação e sessões de protocolo ficam fora do escopo.
- A política pode ser carregada por leitura explícita do resource e reutilizada durante a execução; sua origem deve continuar verificável, sem valor hardcoded.
