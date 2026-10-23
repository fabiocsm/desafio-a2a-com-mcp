# Feature Specification: Conformidade, reprodução e documentação da entrega

**Feature Branch**: `dev` (ramo atual; nenhum ramo criado)

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Permitir que o avaliador reproduza a solução de um clone limpo, confira todos os contratos e encontre evidências reais da ponte." — [entrada completa para $speckit-specify](specify-input.md)

**Feature Directory**: `specs/005-conformidade-entrega`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reproduzir a execução a partir de clone limpo (Priority: P1)

Como avaliador, quero seguir apenas a documentação da entrega para iniciar os dois serviços e obter os mesmos resultados de conformidade.

**Why this priority**: Sem reprodução independente, a implementação não pode ser avaliada como concluída.

**Independent Test**: Clonar a entrega em diretório limpo, seguir somente o README, configurar segredo próprio, iniciar ambos os processos e rodar a validação documentada.

**Acceptance Scenarios**:

1. **Given** um clone limpo com os pré-requisitos documentados, **When** o avaliador segue Como rodar e gera/exporta seu próprio segredo, **Then** instala as dependências nas versões previstas e inicia os dois processos nas portas padrão, sem valores secretos fornecidos pelo autor
2. **Given** os dois processos recém-iniciados, **When** o avaliador executa o validador original pelo comando documentado, **Then** obtém 36 verificações passando e código de saída 0
3. **Given** uma validação anterior alterou reservas em memória, **When** o avaliador precisa repetir a execução, **Then** a documentação orienta reiniciar ambos os processos antes da nova validação, preservando a chave quando testar retomada após restart MCP

---

### User Story 2 - Auditar a ponte e as proteções exigidas (Priority: P1)

Como avaliador, quero localizar a passagem de estado entre os serviços e comprovar as proteções que o validador automático não demonstra sozinho.

**Why this priority**: O sucesso automático não cobre reinício de processo nem toda a evidência de rastreamento e integridade.

**Independent Test**: Seguir o fluxo manual do enunciado e registrar evidências com os resultados esperados, além da execução automática completa.

**Acceptance Scenarios**:

1. **Given** um pedido A2A com o trace-id informado na validação, **When** o avaliador examina o stderr do MCP, **Then** localiza tools/list do agente antes do primeiro tools/call do agente, o mesmo trace-id e ids distintos na chamada inicial e no retry, sem confundir a descoberta do cliente direto do validador com a do agente
2. **Given** um estado válido capturado diretamente do MCP, **When** o avaliador reinicia somente o servidor com a mesma chave e envia o retry antes da expiração, **Then** a reserva conclui sem recuperar estado em memória do servidor
3. **Given** estados adulterados/expirados, argumentos adulterados e capability form ausente em cenários separados, **When** o avaliador repete os pedidos previstos, **Then** estados adulterados/expirados recebem -32602, conflito que exige elicitation sem form recebe -32021 com HTTP 400 e requiredCapabilities, e argumentos divergentes são rejeitados ou substituídos pelos valores selados, sem reserva com dados adulterados; ambas as estratégias de proteção dos argumentos são aceitas
4. **Given** uma pausa A2A, uma escolha inválida, uma recusa e duas Tasks simultaneamente pausadas, **When** o avaliador segue cada cenário, **Then** observa a lista exata, os estados esperados e a separação das reservas, sem exposição de requestState

---

### User Story 3 - Entregar documentação fiel e repositório íntegro (Priority: P2)

Como responsável pela entrega, quero publicar evidências e instruções fiéis ao código para que a revisão não dependa de explicações adicionais.

**Why this priority**: Transforma uma execução local em um entregável verificável pelo avaliador.

**Independent Test**: Revisar as quatro seções do README, os pontos de código citados, a saída real mais recente, o diff dos arquivos protegidos e a localização final da entrega.

**Acceptance Scenarios**:

1. **Given** a implementação concluída, **When** o responsável prepara o README final, **Then** as quatro seções exigidas contêm comandos verificados, pontos reais da ponte, decisões técnicas e saída completa real da última validação
2. **Given** uma limitação real do SDK, **When** o responsável a documenta, **Then** inclui trecho de evidência e o impacto sem reescrever o protocolo nem declarar cumprido um critério ausente
3. **Given** o repositório pronto para entrega, **When** o avaliador acessa o link do fork público na main, **Then** encontra os dois processos, a estrutura original e dados/validador/exemplos inalterados, sem segredos publicados

### Edge Cases

- Rodar o validador duas vezes sem reinício pode alterar os resultados porque ele cria reservas; isso deve ser explicado, não corrigido modificando o validador.
- O teste de restart do MCP exige a mesma chave entre emissão e retry, mas não depende de reservas transitórias sobreviverem ao processo.
- A saída de validação documentada precisa pertencer à versão entregue; transcrição fictícia ou saída parcial não é evidência.
- Scripts auxiliares podem estar na raiz, mas não podem colapsar os dois serviços em um processo.
- A ausência de qualquer requisito obrigatório deve ser registrada como pendência; evidência de limitação de SDK não concede dispensa automática.
- Dados protegidos e contrato original continuam obrigatórios quando o README do starter for substituído.
- A documentação não deve prometer persistência de reservas ou Tasks após restart quando isso não existe.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A entrega DEVE fornecer comandos exatos a partir de clone limpo para instalar dependências, iniciar os dois processos e executar o validador, preservando os endpoints e portas padrão.
- **FR-002**: A documentação DEVE informar os pré-requisitos da stack escolhida dentro das alternativas constitucionais e Python 3.10+ para o validador; as versões das dependências DEVEM estar travadas nos manifestos exigidos.
- **FR-003**: O README DEVE ensinar a gerar e exportar REQUEST_STATE_SECRET com pelo menos 32 bytes de aleatoriedade, sem publicar o valor usado, e explicar seu uso consistente no teste de retomada após restart MCP.
- **FR-004**: A validação DEVE usar `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` com ambos os processos recém-iniciados, obtendo as 36 verificações passando e saída 0; uma nova rodada DEVE reiniciar ambos para restaurar a base.
- **FR-005**: A entrega DEVE fornecer evidência de tools/list antes da primeira chamada de tool, preservação do trace-id A2A em stderr MCP e ids JSON-RPC diferentes para chamada original e retry.
- **FR-006**: A verificação manual DEVE demonstrar retry após restart do MCP com a mesma chave, rejeição de estado adulterado ou expirado, proteção contra argumentos adulterados e rejeição por capability de formulário ausente.
- **FR-007**: A revisão DEVE demonstrar reserva direta, pausa com texto exato, escolha válida, escolha inválida, recusa, erro de domínio visível no histórico, estados terminais definitivos, isolamento de duas Tasks pausadas e ausência de requestState nas respostas A2A.
- **FR-008**: O README final DEVE conter **Como rodar**, **Onde a ponte acontece**, **Decisões técnicas** e **Saída do validador**; a seção da ponte DEVE apontar os pontos reais do código que convertem input_required em pausa e reenviam requestState.
- **FR-009**: As decisões técnicas DEVEM documentar a proteção efetivamente usada no estado, sua duração e o local de armazenamento das Tasks, sem prometer persistência não exigida.
- **FR-010**: A seção Saída do validador DEVE conter a saída completa real da última execução sobre a versão entregue, em bloco de código, sem resultados fabricados ou declarações de validação ainda não executada.
- **FR-011**: `dados/`, `validador/` e `exemplos/` DEVEM permanecer inalterados e em suas posições. A estrutura com servidor-mcp/ e agente/ DEVE ser preservada e ambos DEVEM continuar processos separados por HTTP.
- **FR-012**: A solução DEVE ser entregue por link de um único repositório público no GitHub, fork do starter, com toda a entrega na main, sem LLM, segredo hardcoded ou dependência de SDK de provedor de LLM.
- **FR-013**: Limitações reais do SDK DEVEM ser documentadas com trecho de evidência e impacto, sem reescrita de protocolo ou declaração de conformidade de requisito ausente.
- **FR-014**: A entrega NÃO DEVE introduzir autenticação, streaming A2A ou SSE de produto, interface gráfica, containers, compose, deploy, gateway, banco de dados, persistência em disco das reservas ou spans/atributos OpenTelemetry, conforme todas as exclusões da constituição. O transporte MCP Streamable HTTP permanece obrigatório; a mera presença de dependências transitivas não habilita recursos excluídos.

### Key Entities *(include if feature involves data)*

- **Entrega**: Versão reproduzível do fork público na main com estrutura e contratos preservados.
- **Instruções de execução**: Pré-requisitos, configuração e comandos exatos para dois serviços e validação.
- **Evidência de conformidade**: Saída integral real da validação e registros dos cenários manuais aplicáveis.
- **Documentação da ponte**: Localização do código e decisões reais de estado, integridade e armazenamento.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um avaliador consegue iniciar e verificar a solução a partir de um clone limpo usando apenas as instruções entregues, sem informação privada adicional do autor.
- **SC-002**: Todas as 36 verificações oficiais passam na execução registrada, com zero falhas e encerramento bem-sucedido.
- **SC-003**: 100% dos cenários manuais previstos nesta spec têm resultado verificável e não contradizem os resultados automáticos.
- **SC-004**: As quatro seções obrigatórias da documentação estão completas e coerentes com a versão entregue, sem resultados inventados ou segredos publicados.
- **SC-005**: Nenhum arquivo protegido foi alterado, e o avaliador acessa todos os artefatos no único repositório público indicado.

## Assumptions

- Depende das capacidades implementadas em [001](../001-servidor-mcp-salas/spec.md), [002](../002-reserva-mrtr-segura/spec.md), [003](../003-agente-a2a-reservas/spec.md) e [004](../004-ponte-a2a-mrtr/spec.md).
- A aceitação da 005 exige teste de wire aprovado para 003/FR-008, verificando elicitation.form como objeto em cada request. Capabilities adicionais, como elicitation.url, são permitidas e não bloqueiam a entrega.
- Todos os cinco princípios constitucionais se aplicam; esta feature encerra a demonstração de conformidade e não concentra correções funcionais sem rastreabilidade às specs de origem.
- Esta etapa gera somente requisitos de entrega; a execução real e a substituição do README ocorrerão durante a implementação desta feature.
- A validação original e seus dados são a referência externa; os resultados não serão simulados para preencher documentação.
- Não se exige pipeline de CI, deploy, containerização ou publicação de serviço acessível na internet.
- A entrega final ocorre na main; branches de desenvolvimento não são criadas por esta especificação.
