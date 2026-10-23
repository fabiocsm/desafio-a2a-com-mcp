# Feature Specification: Servidor MCP de salas e reservas diretas

**Feature Branch**: `dev` (ramo atual; nenhum ramo criado)

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Disponibilizar catálogo, política, consulta de disponibilidade e reserva direta por MCP, com contratos e erros verificáveis." — [entrada completa para $speckit-specify](specify-input.md)

**Feature Directory**: `specs/001-servidor-mcp-salas`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Descobrir salas e política de uso (Priority: P1)

Como assistente consumidor, quero conhecer as salas e a política vigente para preparar um pedido de reserva válido.

**Why this priority**: É a capacidade mínima para descobrir o serviço e utilizar seus dados sem uma cópia local do catálogo.

**Independent Test**: Com apenas o servidor iniciado, descobrir as três ferramentas, listar as cinco salas e ler a política, comparando as respostas com os arquivos do starter.

**Acceptance Scenarios**:

1. **Given** o servidor iniciado com os dados originais, **When** um consumidor descobre as ferramentas e lista as salas, **Then** as três ferramentas têm schemas de entrada de objeto, e as cinco salas são devolvidas com id, nome, capacidade e recursos em dados estruturados e texto equivalentes
2. **Given** a política original disponível, **When** o consumidor lê politica://uso, **Then** recebe o texto integral com tipo text/markdown e versão declarada na primeira linha
3. **Given** um nome de ferramenta ou URI inexistente, **When** o consumidor tenta acessá-lo, **Then** a ferramenta é recusada com -32602 ou isError, conforme o SDK, e a URI recebe -32602 sem lista vazia de conteúdos

---

### User Story 2 - Consultar e reservar um horário livre (Priority: P1)

Como responsável por uma reunião, quero consultar disponibilidade e confirmar um horário livre para que futuras consultas reflitam minha reserva.

**Why this priority**: Entrega o resultado principal sem depender da negociação de alternativas.

**Independent Test**: Consultar sala-aquario em 2026-11-03 das 09:00 às 10:00 (-03:00), reservar para Doc e consultar novamente no mesmo processo.

**Acceptance Scenarios**:

1. **Given** sala-aquario livre das 09:00 às 10:00 no dia 2026-11-03, **When** o consumidor reserva o intervalo para Doc, **Then** a reserva é concluída com sua identificação, sala, início, fim, responsável e versão da política
2. **Given** uma reserva recém-criada, **When** o consumidor consulta o mesmo intervalo, **Then** a sala é informada como ocupada com a reserva em conflito
3. **Given** a reserva inicial de sala-garagem das 14:00 às 15:00, **When** o consumidor consulta esse intervalo, **Then** recebe indisponibilidade e os dados da reserva de Marty sem alterar o estado

---

### User Story 3 - Receber rejeições previsíveis (Priority: P2)

Como consumidor, quero distinguir erro no pedido de erro no uso do protocolo para corrigir minha solicitação sem criar reservas inválidas.

**Why this priority**: Impede resultados silenciosos e garante a compatibilidade com os consumidores externos.

**Independent Test**: Exercitar cada regra de validação tanto na consulta quanto na reserva e enviar requests com metadados ausentes e headers divergentes.

**Acceptance Scenarios**:

1. **Given** sala inexistente, janela violada, duração excessiva ou intervalo vazio/invertido, **When** o consumidor consulta ou reserva, **Then** recebe complete com isError: true e a mensagem exata aplicável, sem nova reserva
2. **Given** um request sem versão ou sem capabilities em _meta, mesmo após outro válido, **When** o servidor o recebe, **Then** rejeita com -32602 e HTTP 400, sem herdar metadados anteriores
3. **Given** headers que contradizem o corpo, **When** o servidor recebe o request, **Then** rejeita a divergência com -32020 e registra método e id em stderr
4. **Given** um request válido com traceparent em _meta, **When** o servidor o recebe, **Then** registra método, id e o valor do traceparent em stderr

### Edge Cases

- Horários exatamente às 08:00 e 20:00 são permitidos quando o intervalo inteiro respeita a janela e o limite de duas horas.
- Intervalo com fim igual ao início deve ser rejeitado, assim como o invertido.
- Uma data anterior ao dia corrente não é motivo de rejeição.
- Consulta de intervalo ocupado apenas informa conflitos; a escolha de alternativas pertence à spec 002.
- Reinício recarrega as reservas originais; não há exigência de recuperar reservas criadas na execução anterior.
- Pedidos em horários adjacentes, sem interseção temporal, não devem ser classificados como sobrepostos.
- Início e fim exigem timezone explícito; instantes com offsets diferentes devem ser convertidos para -03:00 antes de validar a janela no mesmo dia local. Um intervalo que atravessa a noite viola a janela, mesmo que as horas isoladas pareçam permitidas. Formatos inválidos são rejeitados pelo schema/SDK, sem nova mensagem de domínio.
- Quando um pedido viola várias regras, a precedência é sala, intervalo, janela e duração, tanto na consulta quanto na reserva.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O servidor DEVE atender Streamable HTTP em /mcp na porta padrão 7301, permitindo parametrização sem mudar esse padrão.
- **FR-002**: O servidor DEVE declarar capabilities de tools e resources e expor exatamente as capacidades de sala exigidas: listar_salas sem parâmetros, consultar_disponibilidade com sala/inicio/fim e reservar_sala com sala/inicio/fim/responsavel.
- **FR-003**: Toda tool DEVE declarar inputSchema de objeto JSON Schema válido; listar_salas DEVE declarar outputSchema compatível com seu resultado.
- **FR-004**: listar_salas DEVE devolver as cinco salas de dados/salas.json com structuredContent conforme outputSchema e o mesmo JSON serializado em bloco de texto; consulta e reserva completas também DEVEM fornecer structuredContent e texto equivalentes.
- **FR-005**: O processo DEVE carregar as reservas iniciais de dados/reservas.json e refletir as novas reservas em consultas posteriores, sem exigência de persistência após restart.
- **FR-006**: Consulta e reserva DEVEM validar existência da sala, intervalo positivo, janela 08:00–20:00 no mesmo dia local em -03:00 e duração de até duas horas. Início e fim DEVEM ter timezone explícito; instantes DEVEM ser convertidos para -03:00 antes de validar a janela, aceitando offsets equivalentes. Formatos inválidos DEVEM ser rejeitados pelo schema/SDK, sem mensagem de domínio adicional. Nenhuma validação DEVE depender da data de hoje.
- **FR-007**: consultar_disponibilidade DEVE informar sala, se está livre e as reservas em conflito, sem criar uma reserva.
- **FR-008**: reservar_sala em intervalo livre e válido DEVE concluir com resultType complete, sem erro, e structuredContent com reserva, reservado verdadeiro, sala, inicio, fim, responsavel e politica.
- **FR-009**: Erros de domínio DEVEM retornar complete com isError: true, preservar no conteúdo as mensagens `Sala inexistente: <id informado>`, `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`, `Duracao acima do limite: a politica permite no maximo 2 horas` ou `Intervalo invalido: fim deve ser posterior a inicio`, conforme a condição, aceitando prefixo do SDK. Para entradas com formato válido que violem várias regras de domínio, consulta e reserva DEVEM aplicar a mesma precedência: sala, intervalo, janela, duração.
- **FR-010**: O resource politica://uso DEVE devolver o conteúdo integral de dados/politica-de-uso.md como text/markdown; resources/read de outra URI DEVE gerar -32602, nunca contents vazio.
- **FR-011**: Tool inexistente DEVE ser recusada com -32602 ou resultado isError: true, conforme a alternativa aceita para o SDK.
- **FR-012**: Todo request DEVE exigir io.modelcontextprotocol/protocolVersion e io.modelcontextprotocol/clientCapabilities em _meta; ausência de qualquer campo DEVE gerar -32602 e HTTP 400 independentemente das chamadas anteriores.
- **FR-013**: O transporte DEVE rejeitar com -32020 divergências entre o corpo e MCP-Protocol-Version, Mcp-Method e Mcp-Name quando aplicável, conforme os contratos fornecidos.
- **FR-014**: Cada request recebido DEVE produzir registro em stderr com método, id e traceparent quando presente em _meta.
- **FR-015**: O comportamento de reservar_sala sob conflito DEVE ser completado pela spec 002; esta etapa NÃO DEVE criar um contrato alternativo, callback ou sessão para esse caminho.

### Key Entities *(include if feature involves data)*

- **Sala**: Identidade, nome, capacidade e recursos definidos no catálogo fornecido.
- **Reserva**: Identidade, sala, início, fim e responsável; modifica a disponibilidade durante o processo.
- **Política de uso**: Texto e versão fornecidos pelo starter que delimitam os intervalos permitidos.
- **Resultado de disponibilidade**: Sala consultada, indicação de disponibilidade e reservas conflitantes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O consumidor obtém as cinco salas e a política integral em 100% das consultas válidas de catálogo e política.
- **SC-002**: Cada reserva válida de horário livre é confirmada e aparece na consulta seguinte do mesmo processo.
- **SC-003**: As quatro categorias de pedido inválido são recusadas com a mensagem prevista tanto na consulta quanto na reserva, sem criar reservas.
- **SC-004**: 100% das requisições sem os metadados obrigatórios são recusadas, e todas as requisições recebidas podem ser identificadas nos registros por método e id.

## Assumptions

- Não há dependência de outra spec; esta é a primeira entrega incremental, validável diretamente pelo consumidor MCP.
- Dependência futura: [002 — Reserva MRTR segura](../002-reserva-mrtr-segura/spec.md) completa a reserva em conflito. Concluir esta spec não declara o servidor completo perante o desafio.
- Todos os cinco princípios da constituição se aplicam; os contratos principais desta etapa são fronteira MCP, domínio determinístico e rastreabilidade.
- Stack obrigatória e exclusões permanecem na constituição; a escolha entre as stacks aceitas será registrada no planejamento.
- Intervalos adjacentes sem interseção não constituem sobreposição; esse detalhe explicita a interpretação usual da regra existente.
- Autenticação, interface gráfica, armazenamento em disco e negociação A2A não fazem parte desta feature.
