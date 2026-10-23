# Tasks: Servidor MCP de salas e reservas diretas

**Input**: `specs/001-servidor-mcp-salas/` — spec.md, plan.md, research.md, data-model.md, contracts/mcp.md e quickstart.md.
**Prerequisites**: Ler README.md, AGENTS.md, `.specify/memory/constitution.md` e todos os JSON de `exemplos/wire/` antes de implementar.
**Tests**: Os cenários verificáveis da spec e a estratégia do plano serão exercitados com unittest, unittest.mock e HTTP real em subprocessos; escrever os casos de comportamento novo antes da implementação correspondente e constatar a falha inicial; testes que apenas exercitam fundação já implementada são regressões. Não alterar o validador nem adicionar framework de testes.
**Ordem das histórias**: US2 (P1) → US1 (P1) → US3 (P2), preservando os identificadores originais; a descoberta das três tools na US1 depende dos dois handlers reais da US2.
**Organization**: Fases por história, com dependências e checkpoints explícitos. Cada checkbox representa trabalho futuro, não implementação já realizada.

## Formato e caminhos

- Formato: `- [ ] Tnnn [P?] [USn?] descrição com caminho`.
- `[P]` indica arquivos diferentes sem dependência entre as tarefas do mesmo grupo; aguardar os pré-requisitos indicados antes de iniciar o grupo.
- Caminhos de implementação são relativos à raiz. Pacote exclusivo em `servidor-mcp/src/ponte_mcp/`; testes em `servidor-mcp/tests/`.
- `dados/`, `exemplos/` e `validador/` são somente leitura. `agente/` permanece reservado às features seguintes.

## Phase 1: Setup — pacote e suporte aos testes

**Objetivo**: Preparar Python 3.12+, pacote src instalável e ferramentas padrão, sem criar o agente.

- [X] T001 Criar `servidor-mcp/pyproject.toml` com Python >=3.12, mcp==2.3.0, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0; selecionar backend de build compatível com layout src, fixar sua versão exata e configurar instalação editável conforme plan.md, sem extras cli/all/telemetry nem SDK de LLM (FR-001; constituição I/IV).
- [X] T002 [P] Criar o pacote em `servidor-mcp/src/ponte_mcp/__init__.py`, sem efeitos de inicialização no import, mantendo o futuro entrypoint `python -m ponte_mcp` e sem imports de `agente/` (FR-001; constituição I).
- [X] T003 [P] Preparar em `servidor-mcp/tests/test_mcp_http.py` suporte unittest para subir/encerrar subprocesso real, aguardar prontidão com prazo limitado, POST JSON com headers e `_meta` completos por request e capturar stderr; fixtures leem apenas request.body dos exemplos, preservam os arquivos originais e usam estado isolado por cenário (FR-001/012/014; SC-004).

**Checkpoint**: Instalação editável resolve o pacote; o suporte aos testes não exige A2A, rede externa ou alterações em arquivos protegidos.

## Phase 2: Foundational — domínio compartilhado e transporte

**Objetivo**: Criar a base utilizada pelas três histórias. Esta fase bloqueia as seguintes.

- [X] T004 [P] Definir em `servidor-mcp/src/ponte_mcp/modelos.py` os modelos de Sala (`id: str, nome: str, capacidade: int, recursos: list[str]`), Reserva (`id: str, sala: str, inicio: datetime, fim: datetime, responsavel: str`), Política, ListaDeSalas, Disponibilidade (`sala: str, livre: bool, conflitos: list[Conflito]`), Conflito (`id, inicio, fim, responsavel`) e ReservaOut (`reserva: str ou null, reservado: bool, sala/inicio/fim/responsavel/politica: str ou null, motivo: str ou null`), mantendo tipos/nullable do modelo e os campos obrigatórios do wire; saídas de sucesso de reserva preenchem os campos mesmo quando o tipo admite null (FR-003/004/007/008).
- [X] T005 Implementar em `servidor-mcp/src/ponte_mcp/salas.py` carregamento único por instância do processo de `dados/salas.json`, `dados/reservas.json` e `dados/politica-de-uso.md`, resolvendo caminhos pelo pacote instalado em modo editável, sem depender do cwd; preservar o texto integral e extrair a versão da primeira linha; respeitar "cinco registros, ids únicos" e "Reserva.sala referencia uma Sala existente"; iniciar contador sem colisão e não gravar nos arquivos (FR-004/005/010; SC-001/002).
- [X] T006 Criar em `servidor-mcp/src/ponte_mcp/salas.py` uma única validação de sala/intervalo para consulta e reserva, precedida de testes unitários de suas regras em `servidor-mcp/tests/test_salas.py` com falha inicial demonstrada: "Converter os instantes para o offset do domínio -03:00 antes de conferir a janela", "Exigir datas com timezone", "Exigir fim > inicio, duração <= 2h e intervalo dentro da janela do mesmo dia" e "Nenhuma comparação com a data corrente é permitida"; conservar "precedência determinística: sala, intervalo, janela, duração"; formatos inválidos seguem o schema/SDK, sem inventar mensagem de domínio (FR-006/009; SC-003).
- [X] T007 [P] Implementar em `servidor-mcp/src/ponte_mcp/entrada.py` observação ASGI do JSON antes do SDK, com stderr contendo método, id e `_meta.traceparent` quando presente, inclusive em rejeições; exigir os dois campos `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities` em `params._meta` e devolver JSONRPCError/ErrorData oficiais com -32602/HTTP 400 se ausentes; reentregar bytes do body sem alteração, encaminhar demais scopes/lifespan e não inferir dados do header, de sessão ou de outra chamada (FR-012/014; SC-004).
- [X] T008 Construir a factory em `servidor-mcp/src/ponte_mcp/app.py` com MCPServer de nome estável `ponte-salas`, app oficial `streamable_http_app(streamable_http_path='/mcp', json_response=True, stateless_http=True, host=host)` envolto pela entrada ASGI; criar `servidor-mcp/src/ponte_mcp/__main__.py` para Uvicorn com um worker e lifespan intacto, MCP_HOST=127.0.0.1/MCP_PORT=7301 e overrides; ler REQUEST_STATE_SECRET hexadecimal, validar decodificação de pelo menos 32 bytes sem imprimir a chave e preparar configuração estável para a 002, sem implementar MRTR nesta etapa (FR-001/012/014/015; constituição I/II/III).

**Checkpoint**: Transporte oficial disponível, dados em memória, validação compartilhada e entrada observável; as tools são acrescentadas nas histórias seguintes, sem handlers fictícios de conflito.

## Phase 3: User Story 2 — Consultar e reservar um horário livre (P1) — MVP de reserva direta

**Objetivo**: Criar reservas válidas e expor sua influência em consultas subsequentes.
**Teste independente**: Após a fundação, subir MCP limpo, consultar sala-aquario em 2026-11-03 09h–10h (-03:00), reservar para Doc, consultar novamente e conferir conflito. Consultar a reserva inicial de Marty sem alterar estado. A versão da política é comparada ao arquivo original; sua leitura como resource será validada na US1.

### Testes e implementação

- [X] T009 [P] [US2] Escrever em `servidor-mcp/tests/test_salas.py` casos de consulta livre/ocupada, projeção Conflito com id/inicio/fim/responsavel, consulta sem mutação, reserva livre seguida de consulta, ids de reserva únicos sem assumir res-0003, limites 08h/20h/2h, passado, offset equivalente e adjacência sem sobreposição; constatar falha antes de T011–T013 (FR-005/006/007/008; SC-002).
- [X] T010 [P] [US2] Escrever em `servidor-mcp/tests/test_mcp_http.py` a jornada consultar/reservar/consultar usando os argumentos do exemplo 02, verificando todos os campos da reserva e versão da primeira linha da política original; conferir em tools/list as duas tools desta história, schemas de objeto e required correspondentes às assinaturas; constatar falha antes de T014 (FR-002/003/005/007/008; SC-002).
- [X] T011 [US2] Implementar em `servidor-mcp/src/ponte_mcp/salas.py` o cálculo de conflitos compartilhado com a restrição literal "inicio < reserva.fim e fim > reserva.inicio para a mesma sala", retornando projeções sem alterar registros; preservar adjacência e instantes com offsets equivalentes (FR-006/007).
- [X] T012 [US2] Implementar consultar_disponibilidade em `servidor-mcp/src/ponte_mcp/salas.py` com validação única, sala/livre/conflitos e nenhuma mutação, incluindo a reserva inicial de Marty em sala-garagem no dia 2026-11-03 das 14h às 15h (-03:00) (FR-005/006/007).
- [X] T013 [US2] Implementar o caminho livre de reservar_sala em `servidor-mcp/src/ponte_mcp/salas.py`, validando antes de criar, reutilizando o cálculo de conflitos e obedecendo "Uma reserva confirmada entra na coleção em memória antes da resposta, para ficar visível à próxima consulta"; devolver reserva/reservado/sala/inicio/fim/responsavel/politica, sem gravar em disco nem criar callback, sessão, resposta de conflito alternativa ou memória de continuação reservada à 002 (FR-005/006/008/015; SC-002).
- [X] T014 [US2] Registrar em `servidor-mcp/src/ponte_mcp/app.py` consultar_disponibilidade(sala, inicio, fim) e reservar_sala(sala, inicio, fim, responsavel) com schemas gerados pelo SDK e resultados completos contendo structuredContent e o mesmo JSON em texto; manter resultType complete e isError ausente/falso em sucesso; executar T010, incluindo descoberta dos dois handlers reais desta história (FR-002/003/004/007/008).
- [X] T015 [US2] Acrescentar em `servidor-mcp/tests/test_mcp_http.py` cenário de restart real: criar reserva livre, provar visibilidade em consulta no processo atual, reiniciar MCP e comprovar recarga das reservas originais sem exigir a nova reserva; verificar arquivos protegidos inalterados (FR-005; SC-002).
- [X] T016 [US2] Completar em `servidor-mcp/tests/test_mcp_http.py` verificações de equivalência JSON textual/structuredContent para consultar_disponibilidade e reserva concluída, conferindo tipos/campos obrigatórios do modelo, sem fixar a grafia de ids gerados ou forçar variação de outro SDK (FR-003/004/008; SC-002).
- [X] T017 [US2] Executar os testes da US2 e registrar a descoberta de consultar_disponibilidade/reservar_sala, reserva direta/consulta e restart em `specs/001-servidor-mcp-salas/quickstart.md`; deixar explícito que a reserva sob conflito continua sendo o incremento 002 e não possui evidência funcional nesta spec (FR-001/005/007/008/015; SC-002).

**Checkpoint**: US2 completa e verificável diretamente por HTTP: consulta e reserva livre com estado em memória. A US1 acrescenta listar_salas e o resource para completar a descoberta das três tools; MRTR ainda pendente da 002.

## Phase 4: User Story 1 — Descobrir salas e política de uso (P1)

**Objetivo**: Publicar o catálogo original e o resource pelo MCP.
**Teste independente**: Com somente MCP e a US2 concluída, descobrir as três tools reais, listar cinco salas e ler integralmente a política; comparar JSON textual/estruturado e outputSchema. Esta história depende dos handlers da US2 para satisfazer seu teste integral, sem exigir agente ou MRTR.

### Testes e implementação

- [X] T018 [P] [US1] Escrever em `servidor-mcp/tests/test_salas.py` testes de leitura das cinco salas com todos os campos do modelo, ids únicos, política sem perda de bytes e versão da primeira linha, comparando com os arquivos originais; constatar falha antes de T020 (FR-004/010; SC-001).
- [X] T019 [P] [US1] Escrever em `servidor-mcp/tests/test_mcp_http.py` casos reais de tools/list com exatamente as três tools e schemas de objeto/required correspondentes às assinaturas, capabilities tools/resources, listar_salas sem argumentos com outputSchema compatível e structuredContent equivalente ao JSON de content[].text, politica://uso com text/markdown/texto integral e nomes/URIs inexistentes; confrontar a versão do resource com a saída da reserva da US2; constatar falha antes de T021/T022 (FR-002/003/004/010/011; SC-001).
- [X] T020 [US1] Implementar em `servidor-mcp/src/ponte_mcp/salas.py` funções pequenas de catálogo e política sobre os dados carregados, sem mutação, cópia de catálogo no agente ou versão hardcoded; executar T018 (FR-004/010; SC-001).
- [X] T021 [US1] Registrar em `servidor-mcp/src/ponte_mcp/app.py` a tool listar_salas sem parâmetros com modelos de saída que gerem outputSchema e JSON textual equivalente ao structuredContent, e o resource politica://uso com texto integral e mimeType text/markdown; anunciar tools/resources usando o mecanismo oficial do SDK (FR-002/003/004/010; SC-001).
- [X] T022 [US1] Configurar em `servidor-mcp/src/ponte_mcp/app.py` os erros oficiais de ferramenta inexistente (-32602 ou complete/isError) e resource desconhecido (-32602, nunca contents vazio), usando API pública do SDK e sem dispatcher próprio; executar os casos negativos de T019 (FR-010/011).
- [X] T023 [US1] Executar os testes US1+US2 e registrar comandos, resultado e o gate integral das três tools em `specs/001-servidor-mcp-salas/quickstart.md`; conferir no stderr método/id/traceparent das chamadas e preservar distinção entre evidência executada e cenário planejado (FR-004/010/014; SC-001/004).

**Checkpoint**: US1 e US2 completas: três tools reais descobertas, catálogo/contratos conferidos e política integral. Ainda faltam a matriz de rejeições US3 e os gates finais da feature.

## Phase 5: User Story 3 — Receber rejeições previsíveis (P2)

**Objetivo**: Demonstrar as categorias de erro de domínio/protocolo, ausência de mutação em falhas e logs de todas as entradas.
**Teste independente**: Exercitar quatro erros em consulta e reserva; alternar requests válidos/inválidos no mesmo processo; variar cada header separadamente e conferir stderr antes das rejeições.

### Testes e implementação

- [X] T024 [P] [US3] Escrever em `servidor-mcp/tests/test_salas.py` matriz das duas operações para sala inexistente, início/fim fora da janela, duração >2h, fim igual/anterior ao início e passagem da meia-noite; testar limites aceitos, equivalência de offsets, rejeição de datetime sem timezone, precedência sala/intervalo/janela/duração e estado inalterado depois de cada falha, sem inventar mensagem de domínio para formato inválido (FR-006/009; SC-003).
- [X] T025 [P] [US3] Escrever em `servidor-mcp/tests/test_mcp_http.py` matriz -32602/HTTP 400 com cada metadata ausente, ambos ausentes, `_meta` ausente, com/sem header moderno, depois de request válido e depois de capabilities diferentes; testar -32020 para divergências isoladas de MCP-Protocol-Version, Mcp-Method e Mcp-Name em tools/call/resources/read, sem herança de contexto ou fallback para completar o corpo (FR-012/013; SC-004).
- [X] T026 [US3] Acrescentar em `servidor-mcp/tests/test_mcp_http.py` casos de logs em stderr para tools/list, tools/call, resources/read e requests rejeitados por metadata/headers/tool/URI, com/sem traceparent e valores diferentes por chamada; verificar método/id e traceparent exato quando presente, sem publicar segredo ou body completo (FR-014; SC-004).
- [X] T027 [P] [US3] Consolidar em `servidor-mcp/src/ponte_mcp/app.py` o mapeamento de erros de domínio para complete/isError: true com as mensagens exatas `Sala inexistente: <id informado>`, `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`, `Duracao acima do limite: a politica permite no maximo 2 horas` e `Intervalo invalido: fim deve ser posterior a inicio`, aceitando apenas prefixo do SDK; conferir ausência de reserva criada e preservar erros de protocolo separados (FR-009; SC-003).
- [X] T028 [P] [US3] Validar e ajustar somente a guarda/observação em `servidor-mcp/src/ponte_mcp/entrada.py` para passar os casos T025/T026 de presença, sem header moderno, sem herança e rejeição observável; preservar body, scopes e lifespan originais, usando modelos oficiais para a rejeição -32602/HTTP 400 (FR-012/014; SC-004).
- [X] T029 [US3] Conferir a configuração pública do SDK em `servidor-mcp/src/ponte_mcp/app.py` contra a matriz de headers T025 e garantir -32020 pelo transporte oficial; se houver impedimento real, registrar evidência em `specs/001-servidor-mcp-salas/quickstart.md` e manter o gate reprovado até solução compatível, sem reescrever classificador/dispatcher, importar API privada ou modificar dependências (FR-013; constituição V).
- [X] T030 [US3] Conferir e ajustar em `servidor-mcp/src/ponte_mcp/salas.py` a validação compartilhada para satisfazer T024, preservando as mensagens exatas e "Se várias regras forem violadas, usar precedência determinística: sala, intervalo, janela, duração"; consulta não altera estado e erros de reserva não acrescentam registros (FR-006/007/009; SC-003).
- [X] T031 [US3] Executar a regressão completa unittest de domínio e HTTP real e registrar em `specs/001-servidor-mcp-salas/quickstart.md` os resultados da matriz de quatro erros nas duas tools, metadata/headers e stderr, incluindo limitações reais com evidências e sem atribuir PASS a caso não executado (FR-006/009/012/013/014; SC-003/004).

**Checkpoint**: Rejeições e rastreabilidade verificadas com HTTP real; nada em sessão completa metadata ausente.

## Phase 6: Polish — reprodução e passagem para 002

- [X] T032 Acrescentar e executar em `servidor-mcp/tests/test_mcp_http.py` verificações de startup a partir de outro cwd, valores padrão/overrides de host/porta, erro de configuração sem segredo/com hexadecimal inválido/com menos de 32 bytes decodificados e aceitação de segredo válido sem vazamento em stderr; preservar um worker e desligamento limpo (FR-001/005/014; constituição I/III/V).
- [X] T033 Atualizar e executar `specs/001-servidor-mcp-salas/quickstart.md` em ambiente virtual novo com instalação editável e `python -m ponte_mcp`, unittest e curl enviando apenas request.body; documentar geração/exportação de REQUEST_STATE_SECRET com `python3 -c "import secrets; print(secrets.token_hex(32))"`, sem registrar o valor e sem substituir ainda o README final da 005 (FR-001/004/010; SC-001; constituição III/V).
- [X] T034 Conferir o diff e registrar em `specs/001-servidor-mcp-salas/quickstart.md` evidência de que `dados/`, `exemplos/`, `validador/` e a estrutura do starter foram preservados; não introduzir LLM, banco/ORM, autenticação, SSE de produto, containers, persistência ou dependência do agente; se falhar, corrigir somente os arquivos de implementação autorizados antes de concluir (FR-015; constituição I/IV/V).
- [X] T035 Registrar em `specs/001-servidor-mcp-salas/quickstart.md` a revisão dos cinco princípios constitucionais, evidências por FR-001–015/SC-001–004 e pendências de MRTR/host/A2A/ponte/entrega para specs 002–005; vincular a evidência de limitação de SDK à futura seção do README e manter o gate final das 36 verificações reservado à integração com os dois processos recém-iniciados, sem declarar o desafio entregue (FR-015; constituição I–V).

## Dependências e ordem de execução

```text
Setup T001 → {T002, T003}
  → Foundational {T004, T007} → T005 → T006 → T008
  → US2 T009–T017 (P1: consulta/reserva direta)
  → US1 T018–T023 (P1: catálogo/resource + descoberta das três tools)
  → US3 T024–T031 (P2: rejeições e regressão)
  → Polish T032–T035 → incremento 001 pronto para 002
```

- T005 depende de T004. T006 depende de T004/T005. T007 pode acompanhar T004–T006; T008 aguarda todos.
- As duas histórias P1 mantêm seus números da spec; US2 precede US1 porque a descoberta integral da US1 exige os três handlers reais. A US2 depende apenas da fundação, que já carrega a política. Nenhuma história depende de A2A ou MRTR para seu teste.
- Após T008, T009/T010 podem ser escritos juntos; T011 → T012 → T013 → T014 são sequenciais no domínio/registro. T015/T016 seguem T014 e T017 fecha a reserva direta/consulta/restart.
- Após T017, T018/T019 podem ser escritos juntos; T020 aguarda T018, T021 aguarda T019/T020 e T022 aguarda T021. T023 valida integralmente as três tools e o resource.
- US3 depende dos handlers das duas histórias P1. T024/T025 podem ser escritos juntos; T026 sucede T025 no mesmo arquivo. T027/T028 podem acompanhar um ao outro após T024–T026. T029 aguarda T027; T030 usa o domínio e os testes já existentes; T031 aguarda todas as correções.
- Não executar alterações simultâneas em salas.py, app.py ou test_mcp_http.py. `[P]` não autoriza pular a ordem das fases. Os testes de comportamento novo antecedem a implementação correspondente; casos sobre a fundação já implementada são regressões e não exigem quebrar código para simular falha.
- Features seguintes não são dependências de conclusão desta base: a 002 completa MRTR; 003/004 entregam host/A2A/ponte; a aceitação integral e README final pertencem à 005.

## Exemplos de execução paralela por história

### US2 — primeira P1 implementada

Após T008: escrever T009 em `servidor-mcp/tests/test_salas.py` e T010 em `servidor-mcp/tests/test_mcp_http.py` em paralelo. T011–T013 compartilham salas.py e devem permanecer sequenciais; T014 integra depois deles.

### US1

Após T017: escrever T018 em `servidor-mcp/tests/test_salas.py` e T019 em `servidor-mcp/tests/test_mcp_http.py` em paralelo. Depois, executar T020–T023 na ordem. Não paralelizar T021/T022, que editam app.py.

### US3

Após T023: escrever T024 em `servidor-mcp/tests/test_salas.py` e T025 em `servidor-mcp/tests/test_mcp_http.py` em paralelo; T026 aguarda T025. Após os testes, T027 em app.py e T028 em entrada.py são independentes; conferir T029 depois de T027.

## Estratégia de implementação

1. Concluir setup/fundação e entregar a US2 como MVP de reserva direta. Seu teste usa apenas MCP: consultar, reservar horário livre, consultar o conflito criado e verificar restart.
2. Concluir US1 e demonstrar sua aceitação integral: três tools descobertas, cinco salas e resource original. A ordem entre histórias de mesma prioridade decorre da dependência de descoberta; não criar handlers provisórios para satisfazer um checkpoint.
3. Concluir US3 e a regressão; a guarda/log já entram na fundação para que nenhum incremento dependa de metadata herdada.
4. Executar reprodução e revisão final, mantendo o foco no MCP. Não criar contrato temporário para reserva ocupada; não afirmar que a base passa no desafio integral.
5. Seguir 002 → 003 → 004 → 005. O comando `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` só serve como gate integral com os dois serviços disponíveis; o validador não oferece filtro 01–12.

## Cobertura para análise

| Requisito / critério | Tarefas |
| --- | --- |
| FR-001 | T001, T002, T003, T008, T017, T032, T033 |
| FR-002 | T010, T014, T019, T021 |
| FR-003 | T004, T010, T014, T016, T019, T021 |
| FR-004 | T004, T005, T014, T016, T018, T019, T020, T021, T023, T033 |
| FR-005 | T005, T009, T010, T012, T013, T015, T017, T032 |
| FR-006 | T006, T009, T011, T012, T013, T024, T030, T031 |
| FR-007 | T004, T009, T010, T011, T012, T014, T017, T030 |
| FR-008 | T004, T009, T010, T013, T014, T016, T017 |
| FR-009 | T006, T024, T027, T030, T031 |
| FR-010 | T005, T018, T019, T020, T021, T022, T023, T033 |
| FR-011 | T019, T022 |
| FR-012 | T003, T007, T008, T025, T028, T031 |
| FR-013 | T025, T029, T031 |
| FR-014 | T003, T007, T008, T023, T026, T028, T031, T032 |
| FR-015 | T008, T013, T017, T034 |
| SC-001 | T005, T018, T019, T020, T021, T023, T033 |
| SC-002 | T005, T009, T010, T013, T015, T016, T017 |
| SC-003 | T006, T024, T027, T030, T031 |
| SC-004 | T003, T007, T023, T025, T026, T028, T031 |

**Contagem**: 35 tarefas — setup 3; fundação 5; US1 6; US2 9; US3 8; acabamento 4. Doze tarefas com `[P]`, em seis grupos compatíveis com as dependências acima. T035 também consolida evidências transversais; nenhuma tarefa exige trabalho fora da spec 001.
