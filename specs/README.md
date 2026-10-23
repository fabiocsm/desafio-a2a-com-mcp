# Divisão SDD do desafio A Ponte

## Decisão de escopo

O trabalho será dividido em **cinco specs incrementais**. A divisão acompanha os
resultados verificáveis do README: serviço de salas utilizável, negociação direta
com retomada segura, reserva por agente, ponte completa e entrega reproduzível.

A reserva MRTR tem uma spec própria porque concentra risco de integridade,
capabilities e reinício, e pode ser exercitada diretamente sem A2A. O host MCP e
o caminho direto A2A ficam juntos para entregar uma reserva utilizável por outro
agente. Pausa, escolha e retomada formam uma única feature de ponta a ponta.
A conformidade final tem escopo próprio porque inclui clone limpo, documentação
e evidências manuais além da implementação funcional.

Uma spec única tornaria as revisões grandes demais; separar cada tool, cada erro
ou cada mecanismo de log criaria fragmentos sem uma jornada suficiente. Setup,
dependências e logs são tarefas dos planos das features, sem specs isoladas.
A criação destas specs não implementa o produto nem substitui o README atual.

## Specs e dependências

| Ordem | Spec | Entrega verificável | Depende de | Entrada para specify | Qualidade |
| --- | --- | --- | --- | --- | --- |
| 001 | [Servidor MCP de salas e reservas diretas](001-servidor-mcp-salas/spec.md) | Catálogo, política, consulta e reserva sem conflito | Nenhuma | [Texto completo](001-servidor-mcp-salas/specify-input.md) | [16/16](001-servidor-mcp-salas/checklists/requirements.md) |
| 002 | [Reserva com alternativas e retomada MRTR segura](002-reserva-mrtr-segura/spec.md) | Alternativas, recusa e retomada protegida, inclusive após restart MCP | 001 | [Texto completo](002-reserva-mrtr-segura/specify-input.md) | [16/16](002-reserva-mrtr-segura/checklists/requirements.md) |
| 003 | [Agente A2A para descoberta e reservas diretas](003-agente-a2a-reservas/spec.md) | Descoberta do agente, reserva direta, Task, artifact e falhas | 001 | [Texto completo](003-agente-a2a-reservas/specify-input.md) | [16/16](003-agente-a2a-reservas/checklists/requirements.md) |
| 004 | [Ponte A2A–MRTR com pausa e retomada por Task](004-ponte-a2a-mrtr/spec.md) | Pausa A2A, escolha, retomada, cancelamento e isolamento por Task | 002 e 003 | [Texto completo](004-ponte-a2a-mrtr/specify-input.md) | [16/16](004-ponte-a2a-mrtr/checklists/requirements.md) |
| 005 | [Conformidade, reprodução e documentação da entrega](005-conformidade-entrega/spec.md) | 36 verificações, cenários manuais, documentação e clone limpo | 001–004 | [Texto completo](005-conformidade-entrega/specify-input.md) | [16/16](005-conformidade-entrega/checklists/requirements.md) |

A ordem recomendada é **001 → 002 → 003 → 004 → 005**. A spec 003 depende
funcionalmente apenas da base 001 para o caminho livre; a spec 004 reúne os
contratos de 002 e 003. As specs intermediárias não declaram a solução completa
nem autorizam criar comportamentos provisórios incompatíveis para fluxos restantes.

## Entradas de geração

Cada feature possui um specify-input.md com o texto integral utilizado como
entrada para $speckit-specify. Cada geração foi executada separadamente,
resolvendo o template ativo e mantendo a numeração sequencial configurada.
Os diretórios já existem: os textos servem para revisão/reprodução do escopo,
não para gerar outras cinco features duplicadas.

As specs mantêm os títulos e a ordem de seções do template ativo. Operações,
campos e mensagens de protocolo são requisitos públicos do desafio; linguagens,
estruturas internas e escolhas entre mecanismos permitidos ficam para o plano.
A stack obrigatória e as restrições transversais continuam na
[constituição](../.specify/memory/constitution.md) e em [AGENTS.md](../AGENTS.md).

## Cobertura dos critérios de aceite do README

Cada item abaixo reproduz um critério original e aponta a spec responsável e
seus requisitos. A ordem é a do enunciado; o texto reproduzido mantém a referência
disponível mesmo quando o README for substituído pela documentação da entrega.

| ID | Critério original | Spec e requisitos |
| --- | --- | --- |
| AC-001 | Sobe na porta `7301` em Streamable HTTP e responde a `tools/list` com as três tools | [001](001-servidor-mcp-salas/spec.md) — FR-001, FR-002 |
| AC-002 | Toda tool tem `inputSchema` que é um objeto JSON Schema válido | [001](001-servidor-mcp-salas/spec.md) — FR-003 |
| AC-003 | `listar_salas` devolve `structuredContent` conforme o `outputSchema` declarado e o mesmo JSON serializado em bloco de texto | [001](001-servidor-mcp-salas/spec.md) — FR-004 |
| AC-004 | Request sem `io.modelcontextprotocol/protocolVersion` ou sem `io.modelcontextprotocol/clientCapabilities` recebe `-32602` com HTTP `400` | [001](001-servidor-mcp-salas/spec.md) — FR-012 |
| AC-005 | `tools/call` de tool inexistente é recusado, por `-32602` ou por `isError` | [001](001-servidor-mcp-salas/spec.md) — FR-011 |
| AC-006 | `resources/read` de `politica://uso` devolve o conteúdo de `dados/politica-de-uso.md`, e de URI inexistente devolve `-32602` | [001](001-servidor-mcp-salas/spec.md) — FR-010 |
| AC-007 | Sala inexistente, janela violada, duração acima do limite e intervalo invertido devolvem `isError: true` com as mensagens exatas definidas neste enunciado | [001](001-servidor-mcp-salas/spec.md) — FR-006, FR-009 |
| AC-008 | O stderr do processo registra método, id e `traceparent` de cada request | [001](001-servidor-mcp-salas/spec.md) — FR-014 |
| AC-009 | Reserva em intervalo ocupado devolve `resultType` igual a `input_required`, com uma única entrada em `inputRequests`, em form mode, e um `requestState` presente | [002](002-reserva-mrtr-segura/spec.md) — FR-002, FR-003 |
| AC-010 | O `requestedSchema` é plano e restringe a escolha às alternativas calculadas pela regra do enunciado, na ordem definida | [002](002-reserva-mrtr-segura/spec.md) — FR-001, FR-003 |
| AC-011 | O mesmo pedido, vindo de cliente que não declarou elicitation em form mode, recebe `-32021` com `data.requiredCapabilities` e HTTP `400` | [002](002-reserva-mrtr-segura/spec.md) — FR-005 |
| AC-012 | O retry com `inputResponses` e `requestState` conclui a reserva e devolve `resultType` igual a `complete` | [002](002-reserva-mrtr-segura/spec.md) — FR-009, FR-012 |
| AC-013 | `requestState` adulterado recebe `-32602` | [002](002-reserva-mrtr-segura/spec.md) — FR-010 |
| AC-014 | Um retry com argumentos adulterados não produz reserva com os valores adulterados | [002](002-reserva-mrtr-segura/spec.md) — FR-011 |
| AC-015 | Um retry com `requestState` válido conclui a reserva mesmo que o processo do servidor MCP tenha sido reiniciado entre o `input_required` e o retry | [002](002-reserva-mrtr-segura/spec.md) — FR-008 |
| AC-016 | A chave de integridade vem de `REQUEST_STATE_SECRET`, com no mínimo 32 bytes, e não há segredo hardcoded no código | [002](002-reserva-mrtr-segura/spec.md) — FR-007 |
| AC-017 | Recusa com `action` igual a `decline` conclui sem reservar e sem `isError` | [002](002-reserva-mrtr-segura/spec.md) — FR-013 |
| AC-018 | O log do servidor MCP mostra um `tools/list` antes do primeiro `tools/call` do agente | [003](003-agente-a2a-reservas/spec.md) — FR-006 |
| AC-019 | O log do servidor MCP mostra o `traceparent` com o mesmo trace-id enviado pelo validador no header da chamada A2A | [003](003-agente-a2a-reservas/spec.md) — FR-010 |
| AC-020 | Os requests do agente declaram a capability de elicitation em form mode, permitindo capabilities adicionais do SDK | [003](003-agente-a2a-reservas/spec.md) — FR-008 |
| AC-021 | `GET /.well-known/agent-card.json` responde 200 com um card v1.0 válido | [003](003-agente-a2a-reservas/spec.md) — FR-002 |
| AC-022 | O card declara a interface JSON-RPC com a URL do endpoint e a versão de protocolo `1.0`, e uma skill de `id` `reservar-sala` | [003](003-agente-a2a-reservas/spec.md) — FR-002 |
| AC-023 | `SendMessage` com sala livre termina a Task em `TASK_STATE_COMPLETED` com o artifact `reserva` | [003](003-agente-a2a-reservas/spec.md) — FR-004, FR-011 |
| AC-024 | O artifact traz a reserva criada e o campo `politica` com o valor lido do resource | [003](003-agente-a2a-reservas/spec.md) — FR-007, FR-011 |
| AC-025 | `GetTask` devolve `id`, `contextId`, estado corrente e o artifact quando existir | [003](003-agente-a2a-reservas/spec.md) — FR-013 |
| AC-026 | `SendMessage` referenciando Task em estado terminal é recusado com erro | [004](004-ponte-a2a-mrtr/spec.md) — FR-012 |
| AC-027 | `SendMessage` pedindo uma sala inexistente termina a Task em `TASK_STATE_FAILED`, com a mensagem exata da tool visível no histórico | [003](003-agente-a2a-reservas/spec.md) — FR-012 |
| AC-028 | `SendMessage` pedindo sala ocupada deixa a Task em `TASK_STATE_INPUT_REQUIRED` com a linha `alternativas: ` listando os ids na ordem do `enum` | [004](004-ponte-a2a-mrtr/spec.md) — FR-001, FR-002 |
| AC-029 | A continuação com `escolha=<id>` conclui a Task em `TASK_STATE_COMPLETED` com a reserva na sala escolhida | [004](004-ponte-a2a-mrtr/spec.md) — FR-007, FR-008, FR-009 |
| AC-030 | A continuação com `escolha=recusar` termina a Task em `TASK_STATE_CANCELED` | [004](004-ponte-a2a-mrtr/spec.md) — FR-010 |
| AC-031 | Escolha fora do `enum` mantém a Task em `TASK_STATE_INPUT_REQUIRED` | [004](004-ponte-a2a-mrtr/spec.md) — FR-006 |
| AC-032 | Duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva, sem trocar de `requestState` | [004](004-ponte-a2a-mrtr/spec.md) — FR-013 |
| AC-033 | O `requestState` não aparece em nenhuma resposta A2A | [004](004-ponte-a2a-mrtr/spec.md) — FR-004 |
| AC-034 | `python3 validador/validar.py` passa nas 36 verificações, com os dois processos recém-iniciados, e termina com código de saída 0 | [005](005-conformidade-entrega/spec.md) — FR-004 |
| AC-035 | `dados/`, `validador/` e `exemplos/` não foram alterados | [005](005-conformidade-entrega/spec.md) — FR-011 |
| AC-036 | O agente é determinístico: o mesmo pedido, enviado duas vezes, produz o mesmo resultado, e não há dependência de SDK de provedor de LLM no `package.json` ou no `pyproject.toml` | [003](003-agente-a2a-reservas/spec.md) — FR-005; [004](004-ponte-a2a-mrtr/spec.md) — FR-014 |
| AC-037 | O README tem as quatro seções exigidas, e os comandos funcionam a partir de um clone limpo | [005](005-conformidade-entrega/spec.md) — FR-001, FR-008, FR-009, FR-010 |

## Contratos adicionais e restrições transversais

| Fonte no enunciado | Responsabilidade |
| --- | --- |
| Tecnologias obrigatórias e portas | Constituição; 001 FR-001, 003 FR-002/003 e 005 FR-001/002 |
| Consulta de disponibilidade, reserva livre e persistência no processo | 001 FR-005/006/007/008 |
| Política integral e versão no artifact | 001 FR-010; 003 FR-007/011 |
| Headers espelhados e rejeição -32020 | 001 FR-013; 003 FR-009; 004 FR-016 |
| Formatos fixos de pedido e continuação | 003 FR-005; 004 FR-006/010 |
| Alternativas ordenadas, limite de três e ausência de alternativas | 002 FR-001/003/004 |
| Expiração, integridade, segredo e restart | 002 FR-006/007/008/010/011; 005 FR-003/006 |
| action decline e cancel no MCP | 002 FR-013; 004 FR-010 |
| Estado opaco, retry e ausência de callback | 002 FR-002/009/014; 004 FR-001/003/004/007 |
| Separação de processos e domínio somente no MCP | 001, 003 FR-001 e 004 FR-008/016; constituição |
| Datas passadas e ausência de regra ligada a hoje | 001 FR-006 |
| Ausência de LLM e determinismo | 003 FR-005; 004 FR-014; 005 FR-012 |
| Fora de escopo integral | Constituição e premissas de todas as specs; 005 FR-014 |
| Arquivos protegidos, estrutura, fork público e main | 005 FR-011/012 |
| Limitação real de SDK com evidência, sem reescrever protocolo | 005 FR-013; constituição |

## Relação com o validador

| Verificações originais | Spec que define o comportamento |
| --- | --- |
| 01–12 | 001 |
| 13–20 | 002 |
| 21–26 e 35 | 003 |
| 27–34 e 36 | 004 |
| Execução integral das 36 e evidências de entrega | 005 |

Essa relação organiza responsabilidade; não implica que o validador ofereça
seleção de testes. A validação oficial continua integral, com os dois processos
recém-iniciados. O teste de restart MCP e a conferência de logs exigem evidências
adicionais; o validador automático não os demonstra sozinho. A expiração do estado
e as demais exigências manuais também precisam ser conferidas.

Os exemplos de wire foram capturados em sequência e podem refletir reservas
criadas anteriormente. Por exemplo, o exemplo A2A 08 lista apenas sala-mirante;
no estado inicial do starter, o cenário da sala-garagem das 14:00 às 15:00 deve
oferecer sala-fusca, sala-mirante, conforme o README e a verificação 14.
Não se deve copiar uma lista estática a partir de uma resposta de exemplo.

## Próximo passo no Spec Kit

As cinco specs estão em **Draft**, revisadas para qualidade dos requisitos,
com 16/16 itens satisfeitos em cada checklist e sem esclarecimentos bloqueantes.
Isso não significa implementação ou validação funcional concluída.

A etapa de $speckit-plan foi concluída para as cinco features. A próxima fase é
$speckit-tasks, começando por 001 e respeitando as dependências; depois, para cada
feature, $speckit-analyze e $speckit-implement.
Use $speckit-clarify se surgir uma decisão de produto que o enunciado não resolve.

O arquivo .specify/feature.json foi atualizado por cada geração, como exige
a skill. Após o lote, a seleção foi reposicionada para **001-servidor-mcp-salas**
para que a próxima etapa comece na base, e não na entrega final.
Nenhum branch foi criado ou alterado; as specs foram geradas no ramo existente dev.

Para selecionar outra feature em uma sessão subsequente, informe explicitamente
SPECIFY_FEATURE_DIRECTORY=specs/<diretorio-existente> ao comando/à sessão,
ou atualize somente feature_directory em .specify/feature.json.
A resolução local não depende do nome do branch. A exigência de main se refere
à entrega final do desafio, não à criação destas especificações.

Não há hooks de especificação ou planejamento registrados: .specify/extensions.yml não existe.
A constituição, o README, os dados, os exemplos, o validador e as pastas de aplicação
foram preservados durante esta etapa.

## Planos de implementação

Os cinco planos e seus artefatos de Phase 0/1 foram gerados em 2026-10-22.
A escolha comum é Python 3.12+, MCP 2.3.0 e A2A SDK 1.2.3, com as dependências
HTTP fixadas e armazenamento em memória. O estado MRTR usa o codec oficial
AES-256-GCM com TTL de 600 segundos e chave estável do ambiente.
As fontes primárias e alternativas estão nos arquivos research.md.

| Feature | Plano | Pesquisa | Modelo | Contrato | Validação prevista |
| --- | --- | --- | --- | --- | --- |
| 001 | [plan.md](001-servidor-mcp-salas/plan.md) | [research.md](001-servidor-mcp-salas/research.md) | [data-model.md](001-servidor-mcp-salas/data-model.md) | [contrato](001-servidor-mcp-salas/contracts/mcp.md) | [quickstart.md](001-servidor-mcp-salas/quickstart.md) |
| 002 | [plan.md](002-reserva-mrtr-segura/plan.md) | [research.md](002-reserva-mrtr-segura/research.md) | [data-model.md](002-reserva-mrtr-segura/data-model.md) | [contrato](002-reserva-mrtr-segura/contracts/mrtr.md) | [quickstart.md](002-reserva-mrtr-segura/quickstart.md) |
| 003 | [plan.md](003-agente-a2a-reservas/plan.md) | [research.md](003-agente-a2a-reservas/research.md) | [data-model.md](003-agente-a2a-reservas/data-model.md) | [contrato](003-agente-a2a-reservas/contracts/a2a.md) | [quickstart.md](003-agente-a2a-reservas/quickstart.md) |
| 004 | [plan.md](004-ponte-a2a-mrtr/plan.md) | [research.md](004-ponte-a2a-mrtr/research.md) | [data-model.md](004-ponte-a2a-mrtr/data-model.md) | [contrato](004-ponte-a2a-mrtr/contracts/ponte.md) | [quickstart.md](004-ponte-a2a-mrtr/quickstart.md) |
| 005 | [plan.md](005-conformidade-entrega/plan.md) | [research.md](005-conformidade-entrega/research.md) | [data-model.md](005-conformidade-entrega/data-model.md) | [contrato](005-conformidade-entrega/contracts/entrega.md) | [quickstart.md](005-conformidade-entrega/quickstart.md) |

Os planos preservam os cinco gates constitucionais antes/depois do design.
Os comportamentos verificados dos SDKs estão explícitos: anúncio permitido de
form+url do cliente MCP, logging antes das rejeições, guarda de metadados na borda e perfil A2A que
aceita ausência de A2A-Version no endpoint dedicado do desafio. Não se altera SDK,
validador ou body de requests para esconder essas diferenças.

A resolução de dependências foi verificada sem instalar pacotes no projeto;
isso não equivale a execução dos serviços ou aos 36 PASS oficiais.
Os comandos dos quickstarts são destinados à implementação futura.

A próxima etapa agora é **$speckit-tasks**, começando pela feature 001 e seguindo
as dependências. Nenhum tasks.md ou arquivo de aplicação foi criado por este
planejamento. O branch Git real continua dev, enquanto o campo BRANCH dos
scripts representa o contexto lógico da feature. A feature ativa volta para 001.
