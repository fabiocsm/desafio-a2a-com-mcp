# Tasks: Agente A2A para descoberta e reservas diretas

**Input**: `specs/003-agente-a2a-reservas/` — spec.md, plan.md, research.md, data-model.md, contracts/a2a.md e quickstart.md.
**Prerequisites**: Ler README.md, AGENTS.md, `.specify/memory/constitution.md` e todos os JSON de `exemplos/wire/`. A implementação funcional de 001 é pré-requisito dos testes reais; 002 é recomendada antes de 003, mas o caminho livre não depende de MRTR.
**Tests**: unittest/IsolatedAsyncioTestCase, unittest.mock e HTTP real com subprocessos. Escrever casos novos antes do comportamento correspondente e verificar a falha inicial; regressões da fundação já implementada não exigem provocar falhas artificiais.
**Organization**: US1 (P1) → US2 (P1) → US3 (P2). Checkboxes representam trabalho futuro; este documento não implementa a aplicação.

## Formato e caminhos

- Formato obrigatório: `- [ ] Tnnn [P?] [USn?] descrição com caminho`.
- `[P]` só permite trabalho simultâneo em arquivos diferentes, após os pré-requisitos indicados. Não significa execução de subagentes nesta geração.
- Caminhos relativos à raiz; implementação em `agente/src/ponte_agente/`, testes em `agente/tests/`. Não importar `ponte_mcp`, não carregar dados de salas no agente e não alterar `dados/`, `exemplos/` ou `validador/`.
- Contratos afetados: exemplos 01/02/05 (host, reserva e política), 07/08/09/10 (card, mensagens e formatos Task); exemplos 03/04/06/11 delimitam a integração posterior com 002/004.

## Phase 1: Setup — pacote e suporte de integração

**Objetivo**: Preparar pacote src independente em Python 3.12+, sem inicializar o MCP dentro do agente.

- [X] T001 Criar `agente/pyproject.toml` com Python >=3.12, mcp==2.3.0, a2a-sdk[http-server]==1.2.3, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0; selecionar e fixar versão exata do backend de build compatível com src/editável, sem extras all/telemetry/SQL/gRPC/FastAPI ou SDK de LLM (FR-001/003/005; constituição I/IV).
- [X] T002 [P] Criar `agente/src/ponte_agente/__init__.py` sem efeitos de inicialização no import, preservando o entrypoint futuro `python -m ponte_agente` e a separação de pacotes/processos (FR-001).
- [X] T003 [P] Preparar em `agente/tests/test_agente_direto.py` suporte de integração para iniciar/encerrar MCP e agente como subprocessos independentes, aguardar prontidão com prazo limitado, capturar stderr e chamar HTTP JSON com biblioteca padrão; gerar segredo só no ambiente MCP, isolar reservas por cenário com restart e ler somente request.body dos exemplos, sem modificar arquivos protegidos (FR-001/003; constituição III/V).

**Checkpoint**: Pacote instalável e suporte de testes sem dependência de rede externa durante a execução dos cenários.

## Phase 2: Foundational — identidade, cliente moderno e contexto HTTP

**Objetivo**: Disponibilizar tipos e transporte comuns; esta fase bloqueia todas as histórias.

- [X] T004 Definir em `agente/src/ponte_agente/tasks.py` mapa em memória e registros usando Protobuf `a2a.types.a2a_pb2`, preservando as regras literais de data-model.md: Task "id UUID, context_id UUID, status, history de Message, artifacts"; TaskStatus "state TASK_STATE_*, message opcional e timestamp UTC se emitido"; Message "message_id próprio, role ROLE_USER/ROLE_AGENT, parts, task_id/context_id quando associados"; Part "text, sem campo legado kind"; TaskRecord "Task pública e traceparent original opcional; não conter regras de sala"; RequestTrace "valor original por Task; mesmo trace-id em cada request MCP"; "Nunca reutilizar context_id para criar continuidade entre Tasks distintas" (FR-004/010/013/015).
- [X] T005 Escrever em `agente/tests/test_mcp_host.py` testes do cliente moderno com SDK real e transporte observado: metadados obrigatórios em todo request, headers espelhados, callback defensivo nunca executado e `session.call_tool(..., allow_input_required=True)` devolvendo input_required cru sem retry automático; comparar capabilities com `{"elicitation": {"form": {}}}` e registrar divergências como falha de conformidade, sem afrouxar a asserção para acomodar o SDK (FR-008/009/015; constituição II/III/V).
- [X] T006 Implementar a base de `agente/src/ponte_agente/mcp_host.py` com Client HTTP reutilizável em mode='2026-07-28', abertura/fechamento explícitos, callback defensivo e sessão raw com allow_input_required=True; montar trace meta por operação, sem mutar cliente global, usar transporte/headers oficiais e executar T005; se o pin impedir o contrato exato de capabilities, registrar evidência em `specs/003-agente-a2a-reservas/research.md` e manter o gate FR-008 reprovado até solução por API pública compatível, sem monkeypatch, API privada ou envelope artesanal (FR-001/008/009/010/015).
- [X] T007 Criar factory e entrypoint em `agente/src/ponte_agente/app.py` e `agente/src/ponte_agente/__main__.py` com lifespan que abre/fecha só o cliente MCP, um worker e padrões AGENTE_HOST=127.0.0.1, AGENTE_PORT=7300, MCP_URL=http://127.0.0.1:7301/mcp e A2A_BASE_URL=http://127.0.0.1:7300; usar ServerCallContextBuilder público para contexto 1.0 quando A2A-Version faltar, preservar versão explícita e capturar traceparent por request, sem herança entre Tasks; rotas reais são montadas em T011/T016 (FR-001/003/009/010).

**Checkpoint**: Infraestrutura pronta; T005/T006 não podem receber PASS com capabilities divergentes. Uma limitação documentada não equivale a requisito cumprido.

## Phase 3: User Story 1 — Descobrir o serviço e confirmar uma reserva livre (P1) — MVP

**Objetivo**: Descobrir o card e confirmar reserva por HTTP com artifact verificável.
**Teste independente**: Com dois processos recém-iniciados, GET do card e SendMessage sem taskId para sala-porao em 2026-11-03 09h–10h (-03:00), responsável Doc. Conferir identidades próprias, SUBMITTED/WORKING/COMPLETED e JSON do artifact com política lida do resource.

### Testes

- [X] T008 [P] [US1] Escrever em `agente/tests/test_agente_direto.py` o teste HTTP de card e reserva livre conforme exemplos 07/08/02: HTTP200, supportedInterfaces com URL /a2a/JSONRPC/1.0, identidade/capabilities/skill reservar-sala, result.task, enums TASK_STATE_*/ROLE_*, parts[].text sem kind, id/contextId próprios e artifact reserva; repetir sem A2A-Version e com 1.0 em processos reiniciados, rejeitar versão explícita incompatível e confirmar pelo MCP que a reserva criada afeta a consulta seguinte (FR-001/002/003/004/011; SC-001/002).
- [X] T009 [P] [US1] Escrever em `agente/tests/test_tasks.py` casos de parser fixo, responsável com espaços, entrada malformada sem chamada MCP, ids/contextIds independentes e registro de SUBMITTED antes de WORKING; observar a sequência de transições internamente sem adicionar campos públicos ao wire; não testar regras de horário no parser (FR-004/005; SC-002).

### Implementação

- [X] T010 [P] [US1] Implementar em `agente/src/ponte_agente/mcp_host.py` tools/list explícito antes do primeiro tools/call, percorrendo páginas quando houver cursor, e seleção da definição descoberta de reservar_sala com seus schemas, sem catálogo local ou fallback hardcoded; ler politica://uso e extrair versão da primeira linha; armazenar HostSnapshot com "catálogo de tools descoberto e política/versão lidas explicitamente", permitindo cache de aplicação e passando trace meta em cada operação (FR-006/007/010; SC-001/002).
- [X] T011 [P] [US1] Publicar AgentCard em `agente/src/ponte_agente/app.py` usando create_agent_card_routes e modelos do SDK: "name, description, version, capabilities, supportedInterfaces, skills e modos texto"; AgentInterface "url base configurada + /a2a, protocolBinding JSONRPC, protocolVersion 1.0"; AgentSkill "id reservar-sala, descrição, tags e exemplos do formato fixo"; seguir exemplo 07, sem habilitar streaming/push/card autenticado ou securitySchemes efetivos (FR-002/003/015; SC-001).
- [X] T012 [US1] Implementar ParsedReservation em `agente/src/ponte_agente/handler.py` com "sala, inicio, fim, responsavel extraídos por gramática fixa"; respeitar "os três primeiros valores são tokens sem espaço, responsavel é o restante do texto"; rejeitar formato malformado com erro de parâmetro do SDK antes de criar reserva, sem LLM, interpretação de linguagem natural ou validação de domínio (FR-005; SC-001/002).
- [X] T013 [US1] Implementar em `agente/src/ponte_agente/tasks.py` criação com UUIDs próprios e transições SUBMITTED → WORKING, preservando mensagem original no histórico e registrando Task antes de aguardar HTTP MCP; usar UTC com Z nos timestamps opcionais, mantendo offsets do domínio no JSON textual e sem inferir contexto de request anterior (FR-004/010/013).
- [X] T014 [US1] Implementar on_message_send do RequestHandler público em `agente/src/ponte_agente/handler.py`: interpretar pedido, criar Task, obter catálogo/política e chamar a tool descoberta exclusivamente por HTTP; passar contexto explícito e retornar tipos do SDK, sem copiar dispatcher/serialização; não responder à elicitation nem converter input_required em sucesso/falha provisórios (FR-001/003/004/005/006/007/015; SC-001).
- [X] T015 [US1] Implementar conclusão bem-sucedida em `agente/src/ponte_agente/tasks.py`: Artifact "artifact_id próprio, name reserva, parts com JSON textual da reserva" com reserva/sala/inicio/fim/responsavel efetivamente devolvidos pelo MCP e politica extraída do resource; transitar para TASK_STATE_COMPLETED e acrescentar mensagem ROLE_AGENT ao histórico, sem copiar conteúdo privado do resultado (FR-007/011/015; SC-002).
- [X] T016 [US1] Integrar handler e rotas oficiais em `agente/src/ponte_agente/app.py` via create_jsonrpc_routes(handler, rpc_url='/a2a', enable_v0_3_compat=False), mantendo lifespan e contexto da fundação; fornecer em `agente/src/ponte_agente/handler.py` on_get_task funcional sobre o mapa existente, para que o RequestHandler seja instanciável e consultável desde o MVP; implementar somente os métodos abstratos fora do escopo com UnsupportedOperationError oficial e deixar serialização camelCase, enums e envelopes ao SDK (FR-002/003/005/011/013).
- [X] T017 [US1] Executar testes US1 e registrar em `specs/003-agente-a2a-reservas/quickstart.md` comandos/resultados da descoberta pública e reserva direta, preservando distinção entre tarefas realizadas, gate FR-008 pendente se houver divergência e aceitação final das 36 verificações; não fixar ids ilustrativos (FR-002/004/011; SC-001/002).

**Checkpoint**: MVP de reserva livre funcional se seus gates passarem; o catálogo/política e metadados já existem, sendo auditados integralmente na US3. GetTask já lê o mapa; consulta durante execução, falhas e terminalidade são auditadas/completadas na US2. Pausa/retomada não são escopo deste MVP.

## Phase 4: User Story 2 — Acompanhar resultados e falhas da Task (P1)

**Objetivo**: Consultar operações e preservar falhas e estados definitivos.
**Teste independente**: Consultar Task concluída, em WORKING durante HTTP controlado, e FAILED; falha sala-delorean preserva mensagem original; SendMessage para COMPLETED/FAILED dá erro sem chamada MCP adicional e sem mutação.

### Testes

- [X] T018 [US2] Acrescentar em `agente/tests/test_agente_direto.py` casos reais SendMessage/GetTask de sucesso e sala inexistente, matriz de erros de política com mensagens exatas da constituição e consulta sem artifact; testar Task desconhecida, formato malformado, terminalidade COMPLETED/FAILED e GetTask enquanto HTTP MCP está bloqueado por barreira controlada; aceitar Task direta no result de GetTask, sem exigir wrapper do exemplo 09 (FR-003/005/012/013/014; SC-003/004/005).
- [X] T019 [US2] Acrescentar em `agente/tests/test_tasks.py` casos de estados terminais imutáveis, GetTask sem mutação e falha técnica/protocolo depois de criar Task, verificando FAILED sem artifact e sem conteúdo privado; contar chamadas MCP para provar que envio a terminal é recusado antes de nova execução (FR-012/013/014/015; SC-003/004/005).

### Implementação

- [X] T020 [P] [US2] Completar a consulta on_get_task de `agente/src/ponte_agente/handler.py` para satisfazer T018/T019: consultar o registro antes de qualquer await externo, devolver snapshot dos tipos oficiais com id/contextId/status/history/artifacts atuais inclusive durante WORKING e sem mutar Task, e TaskNotFound do SDK para id desconhecido; não aguardar a conclusão do SendMessage para consultar (FR-003/013; SC-003).
- [X] T021 [P] [US2] Implementar em `agente/src/ponte_agente/tasks.py` guarda de estados TASK_STATE_COMPLETED/TASK_STATE_FAILED e, preventivamente, TASK_STATE_CANCELED; nenhuma transição terminal pode voltar a WORKING; expor consulta como cópia pública sem registro privado e manter ausência de artifact em falhas (FR-013/014/015; SC-003/005).
- [X] T022 [US2] Mapear complete/isError: true para TASK_STATE_FAILED em `agente/src/ponte_agente/handler.py`, anexando mensagem exata da tool no histórico/status.message sem recalcular política; incluir `Sala inexistente: sala-delorean` e as mensagens de janela/duração/intervalo da constituição; verificar guarda terminal antes de HTTP MCP (FR-012/014; SC-004/005).
- [X] T023 [US2] Tratar falhas técnicas/protocolo após criação de Task em `agente/src/ponte_agente/handler.py` com TASK_STATE_FAILED, mensagem pública `Falha ao executar pedido no servidor MCP` e nenhum artifact de sucesso; não serializar exceção bruta ou corpo MCP que possa conter requestState; erro de parâmetro antes de criar Task e TaskNotFound seguem os erros oficiais, sem substituir as mensagens de domínio (FR-012/013/015; SC-003/004).
- [X] T024 [US2] Executar regressão US1+US2 e registrar em `specs/003-agente-a2a-reservas/quickstart.md` evidências de identidade em GetTask, consulta durante WORKING, mensagens exatas, ausência de mutação/chamada em terminal e erros técnicos sem vazamento (FR-012/013/014/015; SC-003/004/005).

**Checkpoint**: Tasks consultáveis e encerradas definitivamente, sem duplicar regras MCP. CANCELED é protegido pela guarda, mas sua produção por recusa pertence à 004.

## Phase 5: User Story 3 — Consumir capacidades descobertas e rastrear o pedido (P2)

**Objetivo**: Demonstrar descoberta real, origem da política, envelope por request e isolamento de trace.
**Teste independente**: Inspecionar HTTP e stderr MCP do primeiro pedido com traceparent; tools/list precede tools/call; politica://uso é lido; todos os requests têm metadata/headers coerentes e o trace-id original. Usar segunda Task com outro trace e terceira sem trace para detectar herança.

### Testes

- [X] T025 [P] [US3] Completar em `agente/tests/test_mcp_host.py` testes de ordem tools/list → tools/call, catálogo paginado, tool de reserva ausente sem fallback, resource cuja primeira linha muda em fixture controlada sem editar dados/, e duas chamadas pelo mesmo cliente com traces diferentes/ausente; observar metadata/headers em todas as operações e garantir que versão da política vem do resource, não do resultado de reserva (FR-006/007/008/009/010; SC-002/005).
- [X] T026 [P] [US3] Acrescentar em `agente/tests/test_agente_direto.py` captura dos requests HTTP reais e stderr MCP para comprovar método/id/traceparent, tools/list antes da primeira tool, resources/read e tools/call com headers coerentes; enviar trace A, trace B e ausência de trace em Tasks independentes; observar wire sem alterar bodies/headers em trânsito ou arquivos protegidos (FR-001/006/007/008/009/010; SC-005).
- [X] T027 [US3] Acrescentar em `agente/tests/test_mcp_host.py` resultado input_required controlado com marcador opaco verificável e callback defensivo instrumentado: retorno cru sem decodificar token, sem callback/retry automático, sem exposição do marcador em serializers públicos de Task/card/artifact/erros; a prova de pausa A2A e eco de token no retry permanece nos testes 004 (FR-015; constituição II/III).

### Implementação e evidência

- [X] T028 [P] [US3] Ajustar `agente/src/ponte_agente/mcp_host.py` conforme T025/T027: metadados obrigatórios em toda operação, header/body espelhados pelo SDK, descoberta usada sem catálogo fixo, cache de catálogo/política apenas como dados de aplicação e trace explícito por chamada; não completar metadados a partir de sessão e não contornar gate FR-008 (FR-006/007/008/009/010/015).
- [X] T029 [P] [US3] Ajustar `agente/src/ponte_agente/app.py` conforme T026 para capturar traceparent no contexto HTTP de cada nova Task e preservar header de versão explícito, sem reutilizar trace global ou usar requests de outras Tasks para completar contexto; não introduzir instrumentação OpenTelemetry (FR-003/010; SC-005).
- [X] T030 [US3] Conferir a fronteira em `agente/src/ponte_agente/handler.py` e `agente/src/ponte_agente/tasks.py`: input_required deve permanecer distinto de complete/isError e disponível para integração 004, sem callback automático, falso terminal ou serialização do resultado MCP bruto; implementar somente a extensão interna necessária, mantendo a pausa/retomada pública reservada à 004 (FR-015).
- [X] T031 [US3] Executar os testes US3 e registrar em `specs/003-agente-a2a-reservas/research.md` a saída observada de capabilities do pin instalado e evidência das APIs públicas, do perfil A2A sem header e do raw MRTR; manter requisito exato/gate FR-008 explicitamente reprovado se houver anúncio adicional, sem afirmar equivalência ou alterar a constituição (FR-008/015; constituição V).
- [X] T032 [US3] Registrar em `specs/003-agente-a2a-reservas/quickstart.md` evidências executadas de descoberta, resource, headers/metadata por request, trace-id no stderr e ausência de herança; incluir resultado de T031 e limitações destinadas ao README da 005, sem tratar limitação documentada como PASS (FR-006/007/008/009/010/015; SC-002/005).

**Checkpoint**: Evidências verificáveis; um teste positivo de form não basta para aprovar FR-008 se a forma declarada divergir do requisito. Pausa e retomada por Task continuam pendentes de 004.

## Phase 6: Polish — reprodução e passagem para a ponte

- [X] T033 Acrescentar e executar em `agente/tests/test_agente_direto.py` regressão de startup em outro cwd, padrões/overrides de host/porta/MCP_URL/A2A_BASE_URL, URLs do card e desligamento limpo; provar que o agente sobe sem REQUEST_STATE_SECRET próprio e não inicia processo MCP nem carrega dados de domínio; manifesto sem LLM/extras fora do escopo (FR-001/002/003/005; constituição I/IV).
- [X] T034 Executar a bateria completa unittest e os comandos de `specs/003-agente-a2a-reservas/quickstart.md` a partir de ambiente virtual novo após implementar 001/003, registrando comandos, status e resultados reais; incluir geração/exportação segura da chave no terminal MCP, sem publicar valor; não sobrescrever README final da 005 (FR-001/003/011/012/013; SC-001/002/003/004/005).
- [X] T035 Revisar diff e registrar em `specs/003-agente-a2a-reservas/quickstart.md` evidências dos cinco princípios: dois processos HTTP, domínio só no MCP, estado explícito/opacidade, ausência de LLM e recursos fora de escopo, arquivos protegidos preservados, contratos e rastreio; pendência de SDK mantém seu gate reprovado até solução compatível (FR-001/005/008/015; constituição I–V).
- [X] T036 Consolidar em `specs/003-agente-a2a-reservas/quickstart.md` cobertura FR-001–015/SC-001–005 e passagem para 004/005; registrar correspondência com verificações oficiais 21–26/35 e terminalidade parcial de 31, mantendo 27–30/32–34/36 e terminalidade após retomada como integração 004; a entrega integral só pode ser declarada depois das 36 verificações com saída 0 e critérios manuais/clone limpo/README/link público da 005 (FR-014/015; constituição V).

## Dependências e ordem de execução

```text
001 implementada → Setup T001 → {T002, T003}
  → Fundação T004 → T005 → T006 → T007
  → US1 {T008, T009} → {T010, T011} → T012 → T013 → T014 → T015 → T016 → T017
  → US2 T018 → T019 → {T020, T021} → T022 → T023 → T024
  → US3 {T025, T026} → T027 → {T028, T029} → T030 → T031 → T032
  → Polish T033 → T034 → T035 → T036 → 004 → 005
```

- A geração deste documento não exige código existente; a implementação real de 001 bloqueia os testes de integração. 002 é a dependência MRTR da 004, não do caminho livre da 003.
- US1 depende da fundação e usa descoberta/resource/metadados desde o início. US3 audita e reforça esses comportamentos; não adia sua implementação mínima para depois do MVP.
- US2 usa as Tasks criadas pela US1; US3 usa as duas histórias P1. Cada teste independente reinicia seu estado e não depende de executar os exemplos anteriores manualmente.
- T008/T009 são arquivos distintos. T010/T011 dependem dos testes e editam módulos distintos. T012–T016 são sequenciais pela composição de parser, transições, handler e artifact.
- T020/T021 aguardam T018/T019 e usam interfaces já definidas em T004/T013. T022 aguarda as duas; T023 sucede T022 no mesmo handler.py.
- T025/T026 são arquivos distintos; T027 sucede T025 no mesmo test_mcp_host.py. T028/T029 aguardam todos os testes US3; T030 aguarda as duas correções. T031/T032 são sequenciais para que a documentação reflita o resultado real.
- Não paralelizar edições do mesmo arquivo. Testes de comportamento novo precedem sua implementação; testes sobre fundação já disponível são regressões.
- Um gate incompatível com o SDK impede declarar conformidade do requisito; não autoriza reescrever protocolo, mascarar asserção ou relaxar FR/constituição.

## Exemplos de execução paralela por história

### US1

Após T007: T008 em `agente/tests/test_agente_direto.py` e T009 em `agente/tests/test_tasks.py`. Depois, T010 em `agente/src/ponte_agente/mcp_host.py` e T011 em `agente/src/ponte_agente/app.py` podem ocorrer juntos. T012–T017 seguem na ordem.

### US2

Após T018/T019: T020 em `agente/src/ponte_agente/handler.py` e T021 em `agente/src/ponte_agente/tasks.py`, usando os contratos de Task existentes. T022/T023 editam handler.py e aguardam a conclusão de ambas.

### US3

Após T024: T025 em `agente/tests/test_mcp_host.py` e T026 em `agente/tests/test_agente_direto.py`. Após T027: T028 em `agente/src/ponte_agente/mcp_host.py` e T029 em `agente/src/ponte_agente/app.py`. Não sobrepor T025/T027 nem T029/T030.

## Estratégia de implementação

1. Implementar 001 e preferencialmente 002 antes do agente, conforme a sequência do desafio; concluir setup/fundação, verificando de início os limites reais do SDK.
2. Entregar US1 como MVP de descoberta pública/reserva livre, com artifact e consumo MCP reais. Validar sem exigir ponte ainda não implementada e sem declarar o desafio concluído.
3. Acrescentar US2 e validar consulta, mensagem de domínio e estados definitivos. Acrescentar US3 e demonstrar o wire e o trace de todas as operações com evidência.
4. Executar reprodução e revisão transversal; se o gate de SDK falhar, manter sua pendência explícita e resolver por API pública compatível antes de declarar conformidade. Documentar evidência não torna o requisito opcional.
5. Seguir para 004: pedido/alternativas/chave/requestState privados por Task, pausa, escolha inválida, retry com id novo, recusa e isolamento. Na 005 executar o validador original integral, critérios manuais, README e clone limpo; não há filtro oficial para executar somente 21–26/35.

## Cobertura para análise

| Requisito / critério | Tarefas |
| --- | --- |
| FR-001 | T001, T002, T003, T006, T007, T008, T014, T026, T033, T035 |
| FR-002 | T008, T011, T016, T017, T033 |
| FR-003 | T001, T003, T007, T008, T011, T014, T016, T018, T020, T029, T033, T034 |
| FR-004 | T004, T008, T009, T013, T014, T017 |
| FR-005 | T001, T009, T012, T014, T016, T018, T033, T035 |
| FR-006 | T010, T014, T025, T026, T028, T032 |
| FR-007 | T010, T014, T015, T025, T026, T028, T032 |
| FR-008 | T005, T006, T025, T026, T028, T031, T032, T035 |
| FR-009 | T005, T006, T007, T025, T026, T028, T032 |
| FR-010 | T004, T006, T007, T010, T013, T025, T026, T028, T029, T032 |
| FR-011 | T008, T015, T016, T017, T034 |
| FR-012 | T018, T019, T022, T023, T024, T034 |
| FR-013 | T004, T013, T016, T018, T019, T020, T021, T023, T024, T034 |
| FR-014 | T018, T019, T021, T022, T024, T036 |
| FR-015 | T004, T005, T006, T011, T014, T015, T019, T021, T023, T024, T027, T028, T030, T031, T032, T035, T036 |
| SC-001 | T008, T010, T011, T012, T014, T017, T034 |
| SC-002 | T008, T009, T010, T012, T015, T017, T025, T032, T034 |
| SC-003 | T018, T019, T020, T021, T023, T024, T034 |
| SC-004 | T018, T019, T022, T023, T024, T034 |
| SC-005 | T018, T019, T021, T022, T024, T025, T026, T029, T032, T034 |

**Contagem**: 36 tarefas — setup 3; fundação 4; US1 10; US2 7; US3 8; acabamento 4. Doze tarefas com `[P]` em seis grupos. Cobertura é associação de trabalho planejado, não evidência de requisito implementado ou teste aprovado.
