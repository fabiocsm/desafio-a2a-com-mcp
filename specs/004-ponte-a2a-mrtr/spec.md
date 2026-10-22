# Feature Specification: Ponte A2A–MRTR com pausa e retomada por Task

**Feature Branch**: `dev` (ramo atual; nenhum ramo criado)

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Converter a solicitação de informação MCP em pausa A2A e retomar a reserva da mesma Task preservando seu estado opaco." — [entrada completa para $speckit-specify](specify-input.md)

**Feature Directory**: `specs/004-ponte-a2a-mrtr`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pausar e confirmar uma sala alternativa (Priority: P1)

Como assistente solicitante, quero receber alternativas quando minha sala está ocupada e confirmar uma escolha na mesma operação, preservando o horário e o responsável.

**Why this priority**: É a ponte que o desafio avalia e não pode ser substituída por uma confirmação automática.

**Independent Test**: Em estado inicial, enviar o pedido de sala-garagem das 14:00 às 15:00 de 2026-11-03 (-03:00), consultar a pausa, escolher sala-fusca e consultar a reserva concluída.

**Acceptance Scenarios**:

1. **Given** sala-garagem ocupada e sala-fusca/sala-mirante livres no intervalo, **When** o cliente envia o pedido inicial, **Then** a Task vai a TASK_STATE_INPUT_REQUIRED com exatamente alternativas: sala-fusca, sala-mirante, sem reserva ou estado opaco exposto
2. **Given** a Task pausada, **When** o cliente executa GetTask, **Then** recebe os mesmos id e contextId e a mesma pergunta na ordem original
3. **Given** a pergunta da Task e escolha=sala-fusca referenciando seu taskId, **When** o agente envia a continuação ao servidor MCP, **Then** usa novo id JSON-RPC, mesma chave e mesmo requestState; conclui a mesma Task em COMPLETED com a reserva de sala-fusca e política no artifact

---

### User Story 2 - Corrigir uma escolha ou recusar (Priority: P1)

Como cliente, quero corrigir uma opção inválida ou recusar as salas propostas sem perder a operação ou criar reserva indesejada.

**Why this priority**: Define o comportamento humano da pausa e os limites entre estado interrompido e terminal.

**Independent Test**: Em negociações separadas, enviar escolha fora das opções e depois uma escolha válida; recusar outra negociação e tentar continuá-la novamente.

**Acceptance Scenarios**:

1. **Given** uma Task pausada oferecendo sala-fusca e sala-mirante, **When** o cliente envia escolha=sala-aquario, **Then** a Task permanece INPUT_REQUIRED e repete byte a byte a lista original, sem reserva
2. **Given** uma Task pausada, **When** o cliente envia escolha=recusar, **Then** o agente envia decline na continuação MCP e termina a Task em CANCELED, sem criar reserva
3. **Given** uma Task COMPLETED, CANCELED ou FAILED, **When** o cliente envia qualquer continuação dirigida a ela, **Then** recebe erro e o estado permanece terminal sem novo pedido de reserva
4. **Given** uma retomada que recebe erro de execução da tool, **When** o agente trata o resultado, **Then** a Task termina FAILED preservando a mensagem original no histórico

---

### User Story 3 - Manter negociações independentes e rastreáveis (Priority: P2)

Como cliente com mais de uma reunião em negociação, quero continuar cada pedido sem misturar horários, responsáveis ou opções.

**Why this priority**: A identidade da Task deve ser a fronteira de armazenamento de estado do agente.

**Independent Test**: Pausar duas Tasks com intervalos diferentes e continuar em ordem inversa; repetir um pedido que apenas pausa e comparar os textos retornados.

**Acceptance Scenarios**:

1. **Given** duas Tasks pausadas, uma para sala-fusca das 16:00 às 17:00 e outra para sala-garagem das 14:00 às 15:00, **When** o cliente escolhe sala-mirante em cada Task, inclusive em ordem inversa, **Then** cada uma conclui com reserva própria, intervalo e responsável originais, sem compartilhar estado
2. **Given** disponibilidade inalterada e dois pedidos textualmente iguais que entram em pausa, **When** o cliente compara as perguntas, **Then** as linhas de alternativas são idênticas byte a byte, apesar das identidades próprias das Tasks
3. **Given** um trace-id associado ao pedido inicial, **When** a continuação chega sem novo header de rastreamento, **Then** as chamadas MCP da continuação preservam o trace-id da Task e o retry usa um id diferente do pedido inicial

### Edge Cases

- Com uma única alternativa emitida como const, a mensagem A2A deve listar apenas essa sala no mesmo formato.
- Escolha inválida não deve consumir o estado opaco nem trocar a chave da pergunta; a negociação continua pertencendo à mesma Task.
- Uma Task pausada não é terminal; uma Task cancelada, concluída ou com falha é terminal.
- As Tasks pausadas simultaneamente usadas na validação têm intervalos distintos; isso não amplia o escopo para corridas de escrita no mesmo intervalo.
- Sem alternativas, o MCP devolve erro de execução: a Task termina FAILED, sem inventar pergunta ou alternativa local.
- A chave de inputRequests varia entre SDKs e execuções; o agente deve preservar a chave efetivamente recebida.
- Se o estado expirar enquanto o usuário decide, o servidor rejeita a retomada; o agente não pode reconstruir ou renovar o estado por conta própria.
- Para erro JSON-RPC na retomada, a operação não pode ser apresentada como concluída nem produzir artifact de sucesso; a política de apresentação de falha técnica será detalhada no planejamento.
- Um restart do agente não precisa preservar Tasks; o requisito de retomada após restart aplica-se ao servidor MCP com o agente/consumidor preservando a continuação.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O agente DEVE converter o resultType input_required do servidor MCP real em TASK_STATE_INPUT_REQUIRED e devolver o controle ao cliente A2A sem responder à pergunta sozinho nem manter a chamada original esperando entrada humana.
- **FR-002**: A mensagem da pausa DEVE ser exatamente `alternativas: <ids separados por virgula e espaco>`, sem prefixos ou saudações, preservando a ordem de enum e aceitando const para uma única opção.
- **FR-003**: O agente DEVE associar exclusivamente à Task o pedido MCP original, a chave de inputRequests, as opções e o requestState recebido.
- **FR-004**: O agente DEVE tratar requestState como opaco: guardar e ecoar sem abrir, interpretar, alterar ou reconstruir, sem expô-lo no card, no histórico, nas mensagens, artifacts ou qualquer resposta A2A.
- **FR-005**: GetTask durante a pausa DEVE devolver a mesma identidade da Task, seu estado corrente e a pergunta com a lista original.
- **FR-006**: Uma continuação DEVE referenciar o mesmo taskId e usar `escolha=<id>`; se a escolha estiver fora das opções, a Task DEVE permanecer INPUT_REQUIRED com a mesma linha de alternativas, sem reservar.
- **FR-007**: Para escolha válida, o agente DEVE repetir o tools/call original com id JSON-RPC novo, inputResponses sob a chave original e requestState inalterado dentro de params; NÃO DEVE substituir os argumentos originais pela sala escolhida.
- **FR-008**: O conteúdo da resposta accept DEVE informar a sala escolhida; a decisão de reservar e as validações continuam exclusivamente no servidor MCP.
- **FR-009**: Após resultado de reserva com sucesso, a mesma Task DEVE terminar em TASK_STATE_COMPLETED com artifact reserva contendo o JSON e a política conforme a spec 003.
- **FR-010**: `escolha=recusar` DEVE ser traduzida em action decline na continuação MCP e concluir a Task em TASK_STATE_CANCELED após a conclusão sem reserva.
- **FR-011**: Resultado isError: true DEVE terminar a Task em TASK_STATE_FAILED com a mensagem exata da tool visível no histórico; falha de retomada NÃO DEVE gerar confirmação indevida.
- **FR-012**: COMPLETED, CANCELED e FAILED DEVEM ser definitivos: SendMessage dirigido a qualquer Task terminal DEVE ser recusado com erro sem novo tools/call de reserva.
- **FR-013**: Duas Tasks pausadas simultaneamente DEVEM poder ser retomadas em qualquer ordem preservando seus estados, horários, responsáveis e reservas distintos.
- **FR-014**: Dois pedidos iguais sem mudança na disponibilidade entre eles DEVEM produzir mensagens de pausa iguais byte a byte, mantendo identidades próprias.
- **FR-015**: Todos os requests MCP da Task, inclusive o retry, DEVEM preservar o trace-id recebido no pedido inicial; a ausência de novo traceparent na continuação não autoriza perder ou compartilhar o contexto com outra Task.
- **FR-016**: Esta feature DEVE usar o servidor MCP separado por HTTP e manter descoberta, política, metadados, capabilities e headers estabelecidos na spec 003.

### Key Entities *(include if feature involves data)*

- **Task pausada**: Operação A2A existente que aguarda decisão e mantém identidade, pergunta e histórico.
- **Continuação por Task**: Associação privada entre pedido original, pergunta, alternativas, estado opaco e contexto de rastreamento.
- **Decisão do cliente**: Texto de escolha ou recusa relacionado à Task existente.
- **Resultado terminal**: Reserva concluída, cancelamento sem reserva ou falha da mesma Task.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um pedido ocupado é concluído em uma sala escolhida pelo cliente mediante duas mensagens válidas, preservando a identidade da operação.
- **SC-002**: 100% das opções inválidas de aceite mantêm a operação pausada e a pergunta original; 100% das recusas encerram a operação sem nova reserva.
- **SC-003**: Duas operações pausadas simultaneamente são concluídas em ordem inversa sem troca de horário, responsável ou reserva.
- **SC-004**: Nenhuma resposta ao cliente revela o estado privado de retomada, e todos os cenários de continuação terminal são recusados.
- **SC-005**: Pedidos iguais que apenas pausam produzem a mesma pergunta byte a byte, e a identificação de rastreamento permanece associada à operação até a conclusão.

## Assumptions

- Depende de [002 — Reserva MRTR segura](../002-reserva-mrtr-segura/spec.md) e [003 — Agente A2A](../003-agente-a2a-reservas/spec.md), sobre a base da spec 001.
- Todos os cinco princípios constitucionais se aplicam; esta feature materializa principalmente estado explícito, opacidade e fronteiras reais.
- As alternativas são extraídas da pergunta MCP e usadas apenas para validar a escolha e apresentar opções; o agente não recalcula disponibilidade ou capacidade.
- Tasks podem permanecer em memória; persistência após restart do agente, continuidade entre Tasks e streaming ficam fora de escopo.
- Entradas seguem o formato fixo; recuperação de Tasks desconhecidas ou mensagens fora do contrato não adiciona novos fluxos de produto.
- Não se exige definição nova de código ou texto exato para falhas de protocolo apresentadas pelo agente; a proteção contra falsa confirmação é obrigatória.
