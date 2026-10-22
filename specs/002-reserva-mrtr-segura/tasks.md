# Tasks: Reserva com alternativas e retomada MRTR segura

**Input**: `specs/002-reserva-mrtr-segura/` — spec.md, plan.md, research.md, data-model.md, contracts/mrtr.md e quickstart.md.
**Prerequisites**: Implementação e gates locais da spec 001 concluídos; ler README.md, AGENTS.md, `.specify/memory/constitution.md` e todos os JSON de `exemplos/wire/` antes de implementar.
**Tests**: Exercitar os cenários de aceite da spec e a estratégia explícita do plano com unittest/IsolatedAsyncioTestCase, unittest.mock, HTTP real e subprocessos. Escrever casos de comportamento novo antes da implementação correspondente; regressões sobre a fundação existente não precisam falhar artificialmente. Não adicionar framework nem modificar o validador.
**Organization**: Setup → fundação → US1 (P1) → US2 (P1) → US3 (P2) → acabamento. Cada checkbox representa trabalho futuro.

## Formato e caminhos

- Formato: `- [ ] Tnnn [P?] [USn?] descrição com caminho`.
- `[P]` identifica tarefas em arquivos distintos sem dependências entre si, após o pré-requisito indicado. Não autoriza antecipar fases.
- Caminhos relativos à raiz; somente o servidor MCP e os documentos desta feature recebem implementação. `agente/` pertence às specs 003/004.
- `dados/`, `exemplos/` e `validador/` são somente leitura. Fixtures sintéticas vivem nos testes, nunca nos JSON originais.

## Phase 1: Setup — verificar a base e preparar o consumidor direto

**Objetivo**: Reutilizar a spec 001, seus pins e transporte oficial, sem recriar infraestrutura.

- [ ] T001 Conferir a instalação editável de `servidor-mcp/pyproject.toml` e executar os gates de `specs/001-servidor-mcp-salas/quickstart.md`: três tools, resource, validação compartilhada, reserva livre, metadata/headers e stderr; exigir Python >=3.12 e os pins mcp==2.3.0, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0; se a base estiver ausente ou reprovada, registrar o bloqueio em `specs/002-reserva-mrtr-segura/quickstart.md` e concluir 001 antes de avançar (FR-014; constituição I/IV/V).
- [ ] T002 Preparar `servidor-mcp/tests/test_mrtr.py` reutilizando o suporte HTTP/subprocesso da 001: prontidão e shutdown com prazo limitado, estado inicial isolado por cenário, descoberta tools/list e leitura de politica://uso antes da negociação; extrair apenas request.body dos exemplos 03/04/06/11, capturar chave/token reais e construir retry com id novo e params.name/arguments originais, inputResponses, requestState opaco, `_meta` completo e headers espelhados em cada request; não instalar callback automático nem importar funções de tools no consumidor HTTP (FR-009/014; constituição I/II/V).
- [ ] T003 [P] Atualizar a preparação de `specs/002-reserva-mrtr-segura/quickstart.md` com instalação da base 001, ativação da .venv em cada terminal e geração/exportação de REQUEST_STATE_SECRET por `python3 -c "import secrets; print(secrets.token_hex(32))"`, sem registrar valor; orientar manter a mesma variável no terminal do servidor ao reiniciar e reservar a saída completa das 36 verificações à spec 005 (FR-007/008/014; constituição III/V).

**Checkpoint**: Base 001 funcional e consumidor HTTP de teste preparado, sem criar o host/agente de produção.

## Phase 2: Foundational — payload e fronteira oficial de segurança

**Objetivo**: Garantir estado protegido desde a primeira emissão. Esta fase bloqueia todas as histórias.

- [ ] T004 Definir em `servidor-mcp/src/ponte_mcp/modelos.py` o payload de retomada de data-model.md, preservando literalmente as restrições: schema_version — "inteiro fixo 1, validado ao reconstruir"; tool_name — "reservar_sala"; original_arguments — "sala, inicio, fim, responsavel originais"; alternatives — "lista ordenada de até três ids oferecidos"; elicitation_key — "identificador atribuído pelo servidor, criado ao emitir a pergunta"; politica — "versão extraída da política original"; serializar dados, nunca referências a objetos/sessões (FR-006/008/011).
- [ ] T005 Configurar em `servidor-mcp/src/ponte_mcp/app.py` RequestStateSecurity(keys=[bytes.fromhex(REQUEST_STATE_SECRET)], ttl=600) no MCPServer de nome/audience estável ponte-salas; aproveitar a validação de segredo da 001 (obrigatório, hex válido, >=32 bytes decodificados), sem fallback ephemeral, codec próprio ou impressão da chave; deixar RequestStateBoundary aplicar AES-256-GCM e claims de emissão/expiração/método/alvo/digest dos argumentos, sem vincular ao id JSON-RPC (FR-006/007/008/010/011).
- [ ] T006 Criar `servidor-mcp/src/ponte_mcp/mrtr.py` como módulo pequeno de coordenação sobre os tipos/contexto públicos do SDK e domínio existente; ambos requestState/inputResponses ausentes indicam inicial, presença de qualquer um exige continuação completa e válida; usar ctx.request_state já verificado pelo SDK e não descriptografá-lo novamente; rejeitar -32602 em campos incompletos, sem fallback inicial/mutação; não criar mapa de negociações, endpoint adicional, sessão, callback nem espera humana (FR-002/006/008/009/011/014).
- [ ] T007 Preparar em `servidor-mcp/src/ponte_mcp/app.py` a integração do handler reservar_sala com o módulo MRTR, encaminhando o contexto corrente e preservando a borda de metadata/log, transporte Streamable HTTP /mcp, schemas e caminho livre da 001; erros MCP de protocolo devem atravessar a fronteira oficial sem conversão genérica para complete/isError (FR-002/009/010/014; constituição II/IV/V).

**Checkpoint**: Infraestrutura de estado autocontido protegida com TTL 600s; nenhuma história pode emitir token desprotegido para completar um incremento.

## Phase 3: User Story 1 — Escolher uma alternativa compatível (P1) — MVP

**Objetivo**: Transformar conflito em pergunta única e confirmar uma opção elegível, preservando o pedido original.
**Teste independente**: Com MCP recém-iniciado e form declarado, reservar sala-garagem em 2026-11-03 14h–15h (-03:00) para Marty; obter sala-fusca, sala-mirante nessa ordem, confirmar sala-fusca com id novo e verificar a reserva por consulta. Não exige A2A nem a conclusão das histórias seguintes para o caminho accept.

### Testes e implementação

- [ ] T008 [P] [US1] Acrescentar em `servidor-mcp/tests/test_salas.py` casos de alternativas livres, capacidade igual/maior, exclusão de sala ocupada/insuficiente, desempate alfabético e limite de três com mais de três elegíveis; usar fixtures sintéticas em memória para os casos não produzidos pelos cinco registros originais, preservando dados/; incluir opção ocupada entre oferta e accept sem mutação, adjacência e offsets equivalentes (FR-001/012; SC-001/002).
- [ ] T009 [P] [US1] Escrever em `servidor-mcp/tests/test_mrtr.py` a jornada original dos exemplos 03/04: input_required, exatamente uma elicitation/create mode form, requestedSchema plano, sala string required e enum na ordem sala-fusca/sala-mirante, token não vazio, nenhuma reserva na emissão; retry accept com chave capturada, id diferente e token literalmente igual; comparar structuredContent com JSON textual, campos reserva/reservado/sala/inicio/fim/responsavel/politica e consulta posterior; incluir conflito sem alternativas e escolha fora do schema sem mutação; ocupar uma opção após a oferta por reserva válida e exigir complete/isError: true sem nova pergunta/sobreposição, sem comparar texto desse erro adicional; não fixar a chave ilustrativa nem o id da reserva (FR-002/003/004/009/012/014; SC-001/002).
- [ ] T010 [US1] Implementar em `servidor-mcp/src/ponte_mcp/salas.py` seleção de alternativas reutilizando a validação/disponibilidade da 001: somente livres no intervalo, capacidade >= sala solicitada, ordenação (capacidade, id), máximo três, sem mutação; quando não houver opções, retornar o erro de domínio `Sem alternativas disponiveis no intervalo` para complete/isError: true, sem elicitation (FR-001/004; SC-001).
- [ ] T011 [US1] Implementar a emissão em `servidor-mcp/src/ponte_mcp/mrtr.py`: construir chave da pergunta pelo servidor, schema plano com sala string obrigatória e enum ordenado, InputRequiredResult com uma única ElicitRequest form e payload completo em request_state; o SDK sela o token e encerra a chamada sem gravar reserva nem chamar o cliente; conferir form do request antes de emitir, concluindo a matriz negativa na US3 (FR-002/003/005/006/008; SC-001).
- [ ] T012 [US1] Implementar accept em `servidor-mcp/src/ponte_mcp/mrtr.py` lendo ctx.input_responses e ctx.request_state: exigir mapa com exatamente a elicitation_key selada (-32602 para mapa vazio, chave divergente ou entrada adicional), action accept e content.sala pertencente às alternativas seladas; recuperar horário/responsável/política originais e encaminhar somente a sala escolhida ao domínio; resposta inválida não cria reserva, escolha fora do schema segue validação do SDK/aplicação sem mensagem de domínio obrigatória (FR-009/011/012/014; SC-002).
- [ ] T013 [US1] Implementar em `servidor-mcp/src/ponte_mcp/salas.py` confirmação da alternativa após revalidar existência, intervalo, política, capacidade e disponibilidade atuais; preservar horário/responsável/política selados, criar id sem colisão e gravar antes de responder; opção ocupada após a oferta termina em complete/isError: true sem nova pergunta, gravação ou sobreposição, com texto não normatizado para esse erro adicional; retornar os campos completos da spec 001 no sucesso e deixar consultas seguintes observarem a nova reserva (FR-011/012; SC-002).
- [ ] T014 [US1] Completar o registro MRTR em `servidor-mcp/src/ponte_mcp/app.py`, mantendo retorno InputRequiredResult cru e complete com structuredContent/JSON textual equivalente; preservar o caminho livre, o erro sem alternativas e os quatro erros exatos de domínio da 001, sem converter -32602/-32021 em isError (FR-002/003/004/010/012).
- [ ] T015 [US1] Executar T008/T009 e a regressão da 001, registrando comandos/resultados em `specs/002-reserva-mrtr-segura/quickstart.md`; conferir stderr com tools/list antes de tools/call, método/id/traceparent corrente em inicial/retry e ids distintos, sem publicar token ou segredo; não declarar a matriz de segurança/recusa concluída antes de US2/US3 (FR-009/014; SC-001/002; constituição V).

**Checkpoint**: Jornada accept funcional com estado já protegido, alternativas corretas e nenhum efeito nas rejeições testadas.

## Phase 4: User Story 2 — Retomar com segurança após reinício (P1)

**Objetivo**: Demonstrar integridade, expiração, binding do pedido e independência de memória de continuação.
**Teste independente**: Gerar negociação real, reiniciar somente MCP com a mesma chave/nome e aceitar antes de 600s; em cenários isolados, adulterar token, expirar por relógio controlado e alterar argumentos, sempre comparando reservas antes/depois.

### Testes e implementação

- [ ] T016 [US2] Acrescentar em `servidor-mcp/tests/test_mrtr.py` as linhas negativas da matriz explícita de spec.md: alterar bytes do token por um caractere e truncá-lo em casos separados; expirar com unittest.mock no relógio efetivamente usado pelo SDK mantendo TTL 600s; adulterar separadamente sala/inicio/fim/responsavel; omitir somente requestState ou somente inputResponses; enviar mapa vazio, chave divergente ou entrada adicional; emitir payload incompatível por fixture interna protegida com schema_version diferente de 1 ou campo obrigatório ausente; exigir -32602, reservas inalteradas e nenhum fallback para pedido inicial; manter demais metadata/headers válidos, id novo e token opaco no consumidor HTTP (FR-006/007/009/010/011/014; SC-003).
- [ ] T017 [P] [US2] Implementar em `servidor-mcp/tests/test_mrtr.py` teste HTTP com restart real: capturar argumentos/chave/token sem abrir, encerrar o processo, iniciar nova instância com o mesmo REQUEST_STATE_SECRET/nome e aceitar com id novo antes de 600s; testar também expiração mantida após restart por relógio controlado, sem dormir dez minutos nem exigir reservas transitórias persistentes; incluir chave trocada rejeitada e ausência de recuperação de store/sessão (FR-006/008/009/010/014; SC-003/004).
- [ ] T018 [P] [US2] Completar a validação de reconstrução em `servidor-mcp/src/ponte_mcp/modelos.py` para aceitar somente schema_version 1, tool_name reservar_sala e todos os campos do payload T004 com seus tipos/restrições; rejeitar payload incompatível antes de encaminhar ao domínio, usando erro oficial -32602, sem criar formato de envelope próprio (FR-006/008/010/011).
- [ ] T019 [US2] Conferir e ajustar `servidor-mcp/src/ponte_mcp/app.py` e `servidor-mcp/src/ponte_mcp/mrtr.py` contra T016/T017: usar binding e rejeições nativos da RequestStateBoundary para integridade, expiração e divergência de argumentos; manter validações de payload/correlação no handler com erros oficiais -32602 e não reiniciar pedido incompleto; preservar chave/nome entre instâncias e ler dados originais do payload verificado, nunca de argumentos divergentes; erros não podem virar -32603 ou complete/isError nem renovar o prazo; se a API pública não atender, registrar evidência e manter gate reprovado, sem modificar SDK ou reescrever protocolo (FR-006/007/008/009/010/011; SC-003/004; constituição V).
- [ ] T020 [US2] Executar a matriz US2 e a regressão US1 em `servidor-mcp/tests/test_mrtr.py`, incluindo startup sem segredo, hex inválido, menos de 32 bytes e segredo válido sem vazamento, aproveitando os testes da 001; registrar comando, resultado e evidência de restart/expiração em `specs/002-reserva-mrtr-segura/quickstart.md`, sem marcar PASS para caso não executado (FR-006/007/008/010/011; SC-003/004).

**Checkpoint**: Retomada comprovada entre processos e rejeições de segurança sem reserva; validade continua contada desde a emissão original.

## Phase 5: User Story 3 — Recusar opções e respeitar capacidades do cliente (P2)

**Objetivo**: Recusa/cancelamento sem erro e form estritamente declarado por request.
**Teste independente**: No mesmo processo, alternar form explícito, capabilities vazias, elicitation genérica e url-only; em negociações separadas responder decline/cancel e comparar consultas. Para candidato único, ocupar sala-fusca via reserva válida antes de pedir sala-garagem 14h–15h, obtendo somente sala-mirante.

### Testes e implementação

- [ ] T021 [US3] Escrever em `servidor-mcp/tests/test_mrtr.py` casos de conflito com clientCapabilities {}, elicitation {} e elicitation somente url, inclusive depois de chamada com form declarado; exigir -32021/HTTP 400 com data.requiredCapabilities={"elicitation":{"form":{}}}, sem elicitation/mutação; distinguir `_meta` obrigatório ausente (-32602/400 herdado da 001) de campo presente sem form; incluir reserva livre e conflito sem alternativas sem exigir form desnecessariamente (FR-004/005).
- [ ] T022 [US3] Acrescentar em `servidor-mcp/tests/test_mrtr.py` negociações reais independentes para decline e cancel com chave/token capturados e id novo, complete, isError ausente/false, reservado false, motivo preenchido e igualdade JSON textual/structuredContent; consultas antes/depois devem preservar todas as reservas anteriores; verificar candidato único com enum de um item ou const e impossibilidade de aceitar outra sala (FR-003/009/012/013/014; SC-005).
- [ ] T023 [US3] Consolidar em `servidor-mcp/src/ponte_mcp/mrtr.py` a checagem de ctx.client_capabilities.elicitation.form antes de cada emissão de pergunta manual, usando presença de form mesmo quando seu valor é {}; sem inferir de sessão/chamada anterior ou aceitar elicitation genérica/url-only; lançar MCPError oficial -32021 com requiredCapabilities e garantir HTTP 400 pelo transporte oficial; preservar complete/isError quando não há alternativa (FR-004/005).
- [ ] T024 [US3] Implementar decline/cancel em `servidor-mcp/src/ponte_mcp/mrtr.py` somente após validar estado e correlacionar a resposta à elicitation_key selada; devolver complete com reservado false e motivo, isError ausente/false, sem criar/remover reservas ou interpretar Tasks; manter sala única restrita por enum/const (FR-003/010/013/014; SC-005).
- [ ] T025 [US3] Ajustar a integração em `servidor-mcp/src/ponte_mcp/app.py` para serializar o resultado de decline/cancel no modelo de saída da 001, com structuredContent e mesmo JSON em texto, sem tratar a recusa como exceção; manter capability como erro JSON-RPC e execuções inválidas de domínio como complete/isError (FR-005/013).
- [ ] T026 [US3] Executar US3 e regressão US1/US2 em `servidor-mcp/tests/test_mrtr.py`; registrar em `specs/002-reserva-mrtr-segura/quickstart.md` matriz de capabilities por chamada, candidato único e ausência de mutação em decline/cancel, sem atribuir à feature a pausa/cancelamento A2A da spec 004 (FR-003/005/013/014; SC-005).

**Checkpoint**: Três histórias aceitas via MCP direto, sem callback e sem depender de agente A2A.

## Phase 6: Polish — regressão, reprodução e passagem à ponte

- [ ] T027 Executar toda a suíte por `python -m unittest discover -s servidor-mcp/tests -v` e registrar resultados em `specs/002-reserva-mrtr-segura/quickstart.md`; cobrir catálogo/resource, consulta/reserva livre e os quatro erros da 001, alternativas/accept/recusa, metadata/headers completos em retries e logs inclusive de erros de estado/capability; corrigir somente arquivos autorizados de `servidor-mcp/` e repetir os casos afetados antes de fechar o gate (FR-001–014; SC-001–005; constituição IV/V).
- [ ] T028 Executar `specs/002-reserva-mrtr-segura/quickstart.md` em .venv nova após instalação editável, partindo da raiz e também iniciando o processo de outro cwd; conferir geração/exportação de segredo sem impressão, comandos curl com request.body, retry real e restart com a mesma configuração; registrar apenas comandos/saídas sanitizadas efetivamente executados (FR-007/008/009/014; SC-004; constituição III/V).
- [ ] T029 Conferir diff e estrutura do starter e registrar em `specs/002-reserva-mrtr-segura/quickstart.md` que dados/, exemplos/ e validador/ não mudaram e que não há LLM, banco, autenticação, persistência de reservas, store de continuação, callback ou alterações em agente/; revisar o consumidor de teste para guardar/ecoar requestState sem abrir ou reconstruir (FR-002/008/014; constituição I–IV).
- [ ] T030 Consolidar em `specs/002-reserva-mrtr-segura/quickstart.md` evidências FR-001–014/SC-001–005 e revisão dos cinco princípios, documentando limitações reais do SDK com evidências para o README final; registrar pendências das specs 003/004/005, inclusive isolamento por Task/opacidade A2A e `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` com ambos processos recém-iniciados, 36 PASS/saída 0 e clone limpo na entrega, sem executar gate integral na ausência do agente nem declarar o desafio entregue (FR-014; constituição I–V).

## Dependências e ordem de execução

```text
001 implementada e validada
  → Setup T001 → {T002, T003}
  → Fundação T004 → T005 → T006 → T007
  → US1 {T008, T009} → T010 → T011 → T012 → T013 → T014 → T015
  → US2 T016 → {T017, T018} → T019 → T020
  → US3 T021 → T022 → T023 → T024 → T025 → T026
  → Acabamento T027 → T028 → T029 → T030
  → MRTR pronto para integração da spec 004 (que também depende de 003)
```

- As duas histórias P1 têm ordem explícita: US1 cria a negociação utilizada nos testes US2. US3 depende da emissão/retomada US1 e mantém a segurança consolidada em US2.
- A configuração de segurança já está na fundação. US2 demonstra e endurece o contrato, sem autorizar um MVP com token sem integridade ou chave efêmera.
- T002/T003 aguardam T001; T008/T009 aguardam T007; T017/T018 aguardam T016. Cada par usa arquivos distintos. Demais tarefas seguem a ordem numérica.
- Testes novos precedem a implementação correspondente; testes da infraestrutura já existente são regressões. A validação básica de payload está em T004; T018 trata rejeições de reconstrução cobertas por T016.
- Não editar simultaneamente app.py, mrtr.py ou test_mrtr.py. Nenhuma história 003/004/005 é pré-requisito dos testes diretos desta feature; não duplicar aqui o agente de produção.

## Exemplos de execução paralela por história

### US1

Após T007, escrever T008 em `servidor-mcp/tests/test_salas.py` junto com T009 em `servidor-mcp/tests/test_mrtr.py`. T010–T015 permanecem sequenciais; emissão e accept compartilham mrtr.py.

### US2

Após T016, escrever T017 em `servidor-mcp/tests/test_mrtr.py` junto com T018 em `servidor-mcp/src/ponte_mcp/modelos.py`. O teste de restart utiliza a versão válida do payload da fundação, sem depender do endurecimento de reconstrução; aguardar ambos para T019/T020.

### US3

Não há par seguro entre T021–T026: testes compartilham test_mrtr.py, capability/recusa compartilham mrtr.py e a serialização depende da recusa. Executar sequencialmente; não adicionar marcadores [P] artificiais. O paralelismo da feature concentra-se no setup e nas histórias P1.

## Estratégia de implementação

1. Exigir a base 001 e concluir setup/fundação. Não recriar projeto, transporte ou criptografia.
2. Entregar US1 como MVP MCP: conflito → pergunta → accept → consulta da reserva. Estado protegido, metadata por request e id novo são parte do MVP.
3. Consolidar US2: adulteração, expiração e restart em HTTP real/subprocesso. Preservar o prazo original e rejeitar argumentos divergentes.
4. Concluir US3: capabilities atuais, opção única e decline/cancel sem erro/mutação; executar a regressão integral e reprodução.
5. Passar o contrato opaco às specs 003/004 e evidências à 005. As 36 verificações e a entrega pública na main continuam obrigatórias na integração final, com README exigido e arquivos protegidos intactos.

## Cobertura para análise

| Requisito / critério | Tarefas |
| --- | --- |
| FR-001 | T008, T010 |
| FR-002 | T006, T007, T009, T011, T014, T029 |
| FR-003 | T009, T011, T014, T022, T024 |
| FR-004 | T009, T010, T014, T021, T023 |
| FR-005 | T011, T021, T023, T025, T026 |
| FR-006 | T004, T005, T006, T011, T016, T017, T018, T019, T020 |
| FR-007 | T003, T005, T016, T019, T020, T028 |
| FR-008 | T003, T004, T005, T006, T011, T017, T018, T019, T020, T028, T029 |
| FR-009 | T002, T006, T007, T009, T012, T015, T016, T017, T019, T022, T028 |
| FR-010 | T005, T007, T014, T016, T017, T018, T019, T020, T024 |
| FR-011 | T004, T005, T006, T012, T013, T016, T018, T019, T020 |
| FR-012 | T008, T009, T012, T013, T014, T022 |
| FR-013 | T022, T024, T025, T026 |
| FR-014 | T001, T002, T003, T006, T007, T009, T012, T015, T016, T017, T021, T022, T026, T028, T029, T030 |
| SC-001 | T008, T009, T010, T011, T015 |
| SC-002 | T008, T009, T012, T013, T015 |
| SC-003 | T016, T017, T019, T020 |
| SC-004 | T017, T019, T020, T028 |
| SC-005 | T022, T024, T026 |

**Contagem**: 30 tarefas — setup 3; fundação 4; US1 8; US2 5; US3 6; acabamento 4. Cinco tarefas marcadas [P], em três pares de execução compatíveis com a ordem acima. T027/T030 consolidam cobertura transversal; nenhuma tarefa fica sem requisito ou princípio aplicável.
