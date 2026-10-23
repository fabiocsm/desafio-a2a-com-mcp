# Feature Specification: Reserva com alternativas e retomada MRTR segura

**Feature Branch**: `dev` (ramo atual; nenhum ramo criado)

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Permitir que um consumidor escolha outra sala em caso de conflito e retome a reserva com estado protegido e independente do processo." — [entrada completa para $speckit-specify](specify-input.md)

**Feature Directory**: `specs/002-reserva-mrtr-segura`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Escolher uma alternativa compatível (Priority: P1)

Como solicitante de reserva, quero receber opções de salas equivalentes quando a sala pedida estiver ocupada e confirmar uma delas sem refazer meu pedido.

**Why this priority**: É a capacidade central de negociação que transforma conflito em uma reserva possível.

**Independent Test**: Com o servidor e os dados originais, pedir sala-garagem em 2026-11-03 das 14:00 às 15:00 (-03:00), obter as opções e retomar escolhendo sala-fusca.

**Acceptance Scenarios**:

1. **Given** sala-garagem ocupada das 14:00 às 15:00 e os dados originais carregados, **When** um cliente com suporte a formulário solicita a reserva, **Then** recebe input_required com uma única pergunta e alternativas sala-fusca, sala-mirante nessa ordem, sem criar reserva
2. **Given** a pergunta emitida e sua chave recebida pelo cliente, **When** o cliente envia novo request com a mesma chave, estado inalterado e escolha sala-fusca, **Then** a operação conclui na sala escolhida, preservando horário e responsável do pedido original
3. **Given** uma sala ocupada sem qualquer opção de capacidade suficiente, **When** o cliente solicita reserva, **Then** recebe complete com isError: true e Sem alternativas disponiveis no intervalo, sem pergunta
4. **Given** uma alternativa originalmente oferecida que foi ocupada antes do accept, **When** o consumidor confirma essa alternativa, **Then** recebe complete com isError: true, sem nova pergunta e sem criar reserva sobreposta; o texto desse erro não é fixado pelo desafio

---

### User Story 2 - Retomar com segurança após reinício (Priority: P1)

Como consumidor, quero que a confirmação continue válida após reinício do servidor e que alterações no estado ou no pedido sejam detectadas.

**Why this priority**: O estado retorna pelas mãos do cliente e não pode depender de uma sessão nem permitir adulteração.

**Independent Test**: Capturar um estado válido, reiniciar somente o servidor com a mesma chave e retomar; em cenários separados, adulterar o estado, aguardar sua expiração e adulterar os argumentos.

**Acceptance Scenarios**:

1. **Given** um estado ainda válido e a chave original configurada, **When** o servidor é reiniciado antes de receber a resposta, **Then** o cliente consegue concluir a reserva sem recuperar memória de continuação do processo anterior
2. **Given** um estado adulterado ou expirado, **When** o cliente tenta retomá-lo, **Then** recebe -32602 e nenhuma reserva é criada
3. **Given** um estado válido com horário e responsável selados, **When** o cliente reenvia argumentos diferentes, **Then** a divergência é recusada ou os valores selados prevalecem; os valores adulterados nunca são usados

---

### User Story 3 - Recusar opções e respeitar capacidades do cliente (Priority: P2)

Como consumidor, quero recusar as opções sem tratar minha decisão como falha e receber uma rejeição clara caso eu não suporte o formulário necessário.

**Why this priority**: Mantém a semântica de recusa separada de falha técnica e respeita as capacidades declaradas.

**Independent Test**: Enviar conflito com capabilities vazias e, separadamente, repetir a negociação para decline e cancel, consultando as reservas após cada decisão.

**Acceptance Scenarios**:

1. **Given** um conflito que exige escolha e cliente sem elicitation em form mode, **When** o cliente solicita a reserva, **Then** recebe -32021, HTTP 400 e data.requiredCapabilities identificando a capacidade ausente
2. **Given** uma negociação válida em aberto, **When** o cliente responde decline ou cancel, **Then** recebe complete sem erro, reservado false e motivo, sem nova reserva
3. **Given** um único candidato disponível, **When** o servidor oferece a escolha, **Then** o formulário limita sala àquela opção por enum ou const, sem ampliar as opções

### Edge Cases

- A capacidade de elicitation deve ser conferida na chamada corrente, mesmo que outra chamada anterior a tenha declarado.
- Opções com capacidade insuficiente ou ocupadas no intervalo não podem ser oferecidas.
- Com mais de três candidatas elegíveis, somente as três primeiras da ordenação são oferecidas.
- A chave da pergunta é atribuída pelo servidor; o cliente não deve presumir uma string fixa.
- A expiração vale também após reinício; reiniciar não renova o prazo do estado já emitido.
- Recusa não remove reservas existentes nem consome outra Task; a camada MCP não conhece Tasks.
- Uma escolha que não pertença ao schema não pode criar reserva; o formato da rejeição segue a validação do SDK, sem nova mensagem exata de domínio.
- Um retry com apenas requestState ou apenas inputResponses, mapa vazio, chave diferente da pergunta ou entradas adicionais recebe -32602 e não pode ser tratado como pedido inicial nem criar reserva.
- A disponibilidade é revalidada no accept. Se a opção foi ocupada após a oferta, a operação termina com complete/isError: true, sem nova negociação e sem mutação; o teste não exige texto específico para esse caso adicional.
- A validade do estado após restart não implica persistência das reservas criadas na execução anterior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Em conflito, reservar_sala DEVE calcular salas livres no intervalo, com capacidade igual ou maior que a solicitada, limitar a três e ordenar por capacidade crescente e depois id alfabético.
- **FR-002**: Havendo alternativas, o servidor DEVE retornar resultType input_required, um mapa inputRequests de uma entrada e requestState, sem criar reserva nem iniciar request de retorno ao cliente.
- **FR-003**: A entrada de inputRequests DEVE ser elicitation/create em mode form, com requestedSchema plano, propriedade sala string obrigatória e restrição às alternativas por enum, ou const quando houver uma única alternativa.
- **FR-004**: Sem alternativas, o servidor DEVE retornar complete com isError: true e a mensagem exata `Sem alternativas disponiveis no intervalo`.
- **FR-005**: Quando exigir formulário, o servidor DEVE verificar io.modelcontextprotocol/clientCapabilities no request atual e, sem elicitation em form mode, retornar -32021 com HTTP 400 e data.requiredCapabilities.
- **FR-006**: O requestState DEVE conter os dados necessários para reconstruir o pedido e a continuação, ter integridade protegida por HMAC ou AEAD e expirar entre 5 e 30 minutos; cifrar é opcional.
- **FR-007**: A chave de integridade DEVE vir exclusivamente da configuração REQUEST_STATE_SECRET, representar pelo menos 32 bytes de aleatoriedade e não ser hardcoded nem publicada no repositório.
- **FR-008**: O servidor NÃO DEVE depender de memória de continuação entre input_required e retry. Com estado não expirado e a mesma chave, o retry DEVE funcionar após reinício do processo MCP.
- **FR-009**: O retry do consumidor DEVE usar id JSON-RPC diferente do inicial e enviar inputResponses e requestState em params, preservando a chave recebida em inputRequests. Na retomada, o servidor DEVE exigir os dois campos e exatamente uma resposta com a chave selada; campos incompletos, mapa vazio, chave divergente ou entradas adicionais DEVEM gerar -32602 sem mutação, nunca reiniciar a operação como pedido novo.
- **FR-010**: O servidor DEVE verificar integridade e expiração antes de aplicar a continuação; falhas DEVEM resultar em -32602 e não produzir reserva.
- **FR-011**: O servidor DEVE reconstruir o pedido a partir do estado protegido. Argumentos divergentes DEVEM ser rejeitados ou substituídos pelos valores selados, nunca produzir uma reserva adulterada.
- **FR-012**: Uma resposta accept válida DEVE reservar a alternativa oferecida e preservar horário, responsável e política do pedido original, devolvendo o resultado completo definido na spec 001. Antes de gravar, DEVE revalidar a opção segundo as mesmas regras da reserva. Se a alternativa foi ocupada após a oferta, DEVE terminar em complete com isError: true, sem nova pergunta, sem sobreposição e sem mutação; o texto desse erro adicional não é normatizado.
- **FR-013**: Respostas decline e cancel DEVEM concluir com complete, isError ausente ou false, structuredContent.reservado false e motivo, sem criar reserva.
- **FR-014**: O contrato desta feature NÃO DEVE exigir que o cliente interprete o estado nem definir pausa A2A; essa tradução pertence à spec 004.

### Key Entities *(include if feature involves data)*

- **Solicitação de escolha**: Pergunta identificada por chave do servidor e conjunto ordenado de alternativas elegíveis.
- **Estado de retomada**: Representação protegida do pedido e da continuação, com prazo de validade; opaca para o consumidor.
- **Resposta à escolha**: Decisão accept com sala selecionada, decline ou cancel, ligada à chave da pergunta.
- **Reserva confirmada**: Reserva que preserva o pedido original e usa a sala escolhida dentre as opções oferecidas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: No cenário inicial de sala-garagem das 14:00 às 15:00, o solicitante recebe exatamente duas alternativas na ordem sala-fusca, sala-mirante.
- **SC-002**: Uma escolha válida conclui uma reserva com 100% dos dados originais preservados, exceto a sala explicitamente escolhida.
- **SC-003**: 100% dos estados adulterados ou expirados da matriz de aceite são recusados sem reserva, e nenhum argumento adulterado toma efeito.
- **SC-004**: Um pedido pausado pode ser concluído após reinício do serviço dentro do prazo original, sem solicitar novamente horário ou responsável.
- **SC-005**: Em todos os cenários de recusa, nenhuma reserva nova é criada e a decisão não é apresentada como erro.

### Matriz de aceite de segurança e continuação

Cada linha parte de uma negociação válida isolada; nas rejeições, comparar reservas
antes/depois. Estado/chave da pergunta são capturados da resposta real, sem abrir
o token no consumidor. Campos não envolvidos no caso continuam válidos, inclusive
metadata, headers e o id novo do retry.

| Caso | Variação controlada | Resultado esperado |
| --- | --- | --- |
| Estado adulterado | Trocar um caractere que altere os bytes do token ou truncá-lo, em casos separados | -32602, nenhuma reserva |
| Expiração | Avançar relógio de teste além do TTL de produção de 600s | -32602, nenhuma reserva |
| Expiração após restart | Reiniciar com a mesma chave/nome e testar após o prazo contado da emissão original | -32602, nenhuma reserva; prazo não renovado |
| Argumentos adulterados | Alterar separadamente sala, inicio, fim e responsavel, mantendo token/resposta originais | Nenhum valor adulterado usado; o plano adota -32602, sem reserva |
| Continuação incompleta | Omitir somente requestState ou somente inputResponses | -32602, nenhuma reserva ou nova negociação |
| Correlação inválida | inputResponses vazio, chave trocada ou entrada adicional, em casos separados | -32602, nenhuma reserva |
| Payload incompatível | Fixture interna protegida com schema_version diferente de 1 ou campo obrigatório ausente | -32602, nenhuma reserva; não exige decodificação no consumidor |
| Reinício válido | Mesma chave/nome, estado dentro dos 600s originais e opção ainda livre | complete com reserva dos valores originais e sala escolhida |

Relógio controlado e fixture de payload são recursos exclusivos dos testes; não
criar endpoint/configuração de produção para adulterar estado nem reduzir seu TTL.
SC-003 cobre as linhas negativas e SC-004 cobre o reinício válido. Escolha fora do
schema, capability e decline/cancel são cobertos nos cenários US1/US3.

## Assumptions

- Depende de [001 — Servidor MCP de salas](../001-servidor-mcp-salas/spec.md), que fornece catálogo, validações, consulta, resultados e transporte.
- A implementação da ponte do agente depende desta spec e é definida em [004](../004-ponte-a2a-mrtr/spec.md).
- Todos os princípios constitucionais se aplicam, com foco em estado explícito, integridade e semântica de erros.
- O plano define AEAD AES-256-GCM do SDK e prazo de 600 segundos, dentro das alternativas e da janela permitidas pelos requisitos.
- A mesma chave é mantida entre emissão e retry após restart; rotação de chave, autenticação e persistência de reservas não são exigidas.
- Corridas de escrita no mesmo milissegundo permanecem fora de escopo, sem dispensar as validações existentes.
