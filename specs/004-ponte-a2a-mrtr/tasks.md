# Tasks: Ponte A2A–MRTR com pausa e retomada por Task

**Input**: `specs/004-ponte-a2a-mrtr/{spec.md,plan.md,research.md,data-model.md,quickstart.md,contracts/ponte.md}`.

**Prerequisites**: Implementações e verificações de 001 (MCP), 002 (MRTR seguro) e 003 (host MCP/A2A direto) concluídas. Os diretórios de aplicação ainda estão vazios no starter: este roteiro incrementa as entregas anteriores, não as substitui. Se faltarem, executar seus roteiros antes de T001; não inventar stubs de produção para avançar.

**Tests**: Solicitados pelos testes independentes e cenários de aceite da spec, detalhados no plano/quickstart. Usar `unittest`, `IsolatedAsyncioTestCase` e `unittest.mock`, sem novos pacotes. Escrever os casos de cada história antes da implementação, constatar a falha esperada e executá-los novamente no checkpoint. Doubles servem para resultados controlados; a aceitação exige os dois processos HTTP reais.

**Organization**: Setup → fundação → US1 (P1) → US2 (P1) → US3 (P2) → validação transversal. Todas as tarefas começam pendentes; nenhum teste de aplicação foi executado durante a geração deste roteiro.

## Formato e caminhos

- Cada tarefa segue `- [ ] TNNN [P?] [USn?] Descrição com caminho`.
- `[P]` permite execução simultânea apenas depois dos pré-requisitos indicados, com arquivos distintos. Os testes compartilham `agente/tests/test_ponte.py` e são escritos sequencialmente.
- Código do agente: `agente/src/ponte_agente/`; testes: `agente/tests/test_ponte.py`. Documentação/evidências locais: `specs/004-ponte-a2a-mrtr/quickstart.md`.
- `dados/`, `validador/` e `exemplos/` são entradas imutáveis. O agente não importa `ponte_mcp`, não lê a chave de integridade e não recalcula alternativas ou política.

## Phase 1: Setup — confirmar a base e preparar a verificação

**Objetivo**: Estender os pacotes Python 3.12+ existentes, mantendo os pins de 003, MCP v2/2026-07-28 e A2A v1.0.

- [x] T001 Conferir `agente/pyproject.toml`, `servidor-mcp/pyproject.toml` e os contratos de 001–003 contra `README.md`, `.specify/memory/constitution.md` e todos os arquivos de `exemplos/wire/`; confirmar descoberta, resource, reserva livre, MRTR manual e callbacks defensivos existentes; registrar o gate e pendências em `specs/004-ponte-a2a-mrtr/quickstart.md`, bloqueando avanço se a base não funcionar (FR-016).
- [x] T002 Preparar em `agente/tests/test_ponte.py` o harness de processos HTTP independentes, espera de prontidão, encerramento garantido, leitura dos dados iniciais sem alterá-los e captura privada de requests/resultados e stderr MCP; gerar a chave apenas no ambiente do subprocesso MCP, sem imprimi-la, e reiniciar ambos os serviços entre cenários que exigem base limpa (FR-016; princípio V).

**Checkpoint**: A base responde em `/mcp` (7301), `/a2a` e `/.well-known/agent-card.json` (7300); o harness consegue reproduzir o estado inicial.

## Phase 2: Foundational — separar estado público e continuação privada

**Objetivo**: Disponibilizar os registros usados pelas três histórias sem serializar estado MCP no A2A.

- [x] T003 Ampliar o registro em `agente/src/ponte_agente/tasks.py` com `TaskRecord` e `PendingContinuation`, preservando literalmente as restrições do modelo: `public_task: Task Protobuf, traceparent_original: str opcional, pending: PendingContinuation opcional`; campos privados `tool_name, original_arguments, elicitation_key, ordered_alternatives, pause_text, request_state`; argumentos `sala, inicio, fim, responsavel exatamente como usados na chamada original`; chave de busca: "A chave única de busca do registro é taskId; contextId não substitui a identidade." (FR-003/004/013/015).
- [x] T004 Adaptar `agente/src/ponte_agente/handler.py` e os acessos ao registro de `agente/src/ponte_agente/tasks.py` para que SendMessage/GetTask retornem somente `public_task`, preservem identidades/histórico/artifacts do caminho direto e nunca incorporem PendingContinuation ou token a metadata, mensagens ou erros públicos; manter os serializers/envelopes do SDK e o GetTask direto aceito em 003 (FR-004/005/009/016).

**Checkpoint**: Os registros internos não são modelos públicos; regressões de 003 continuam verificáveis. Todas as histórias dependem desta fase.

## Phase 3: User Story 1 — pausar e confirmar alternativa (Priority: P1) — MVP

**Objetivo**: Converter a resposta MCP em pausa pública e confirmar uma alternativa na mesma Task, com novo request MCP.

**Teste independente**: Com base limpa, pedir sala-garagem em 2026-11-03 14:00–15:00 (-03:00), obter exatamente `alternativas: sala-fusca, sala-mirante`, consultar a pausa, escolher sala-fusca e consultar a mesma Task COMPLETED com artifact e política lida do resource.

### Testes da US1

- [x] T005 [US1] Escrever em `agente/tests/test_ponte.py` testes do formulário recebido: uma entrada `elicitation/create`, mode form, schema plano com sala string obrigatória, ordem de enum preservada, const com opção única, chave variável sem hardcode, token sentinela tratado literalmente e callback defensivo nunca invocado (FR-001/002/003/004).
- [x] T006 [US1] Escrever em `agente/tests/test_ponte.py` o fluxo HTTP pausa → GetTask → accept → GetTask, verificando SUBMITTED/WORKING da base, retorno do controle sem aguardar humano, WORKING consultável durante HTTP de retomada controlado, identidades estáveis, ausência de reserva durante pausa e artifact `reserva` com JSON/versão do resource após sucesso; aceitar GetTask direto ou wrapper conforme 003, sem copiar ids/tokens ilustrativos (FR-001/005/007/008/009/016; SC-001).

### Implementação da US1

- [x] T007 [P] [US1] Implementar em `agente/src/ponte_agente/ponte.py` a leitura somente do InputRequiredResult esperado, extraindo a chave real e sala por enum/const sem consultas de domínio; aplicar "ordered_alternatives vem de enum ou de uma opção const, sem reordenação." e "pause_text = `\"alternativas: \" + \", \".join(ordered_alternatives)`; o prefixo tem exatamente um espaço após os dois-pontos, sem quebra de linha ou texto adicional.", sem saudações ou acesso ao token (FR-001/002/003/004).
- [x] T008 [P] [US1] Ampliar `agente/src/ponte_agente/mcp_host.py` para chamada inicial e retry via `session.call_tool(..., allow_input_required=True)`, passando nome/argumentos originais e `input_responses`/`request_state` para os campos de params do SDK; nunca reenviar envelope/id anterior, usar auto-fulfill ou alterar arguments.sala; renovar metadados/headers de protocolo e capability form em cada request e deixar a sessão atribuir id novo (FR-001/007/008/016).
- [x] T009 [US1] Implementar em `agente/src/ponte_agente/tasks.py` o armazenamento da continuação antes de publicar INPUT_REQUIRED e a preservação de identidade/pergunta/histórico público; cumprir "GetTask não modifica o registro." e "request_state é devolvido literalmente; a criptografia não é conhecida pelo agente." sem armazenar envelope nem depender de contador privado do SDK (FR-003/004/005).
- [x] T010 [US1] Integrar em `agente/src/ponte_agente/handler.py` o retorno cru input_required do host à tradução e ao registro privado, devolver a Task pausada e permitir GetTask durante pausa/HTTP de retomada sem bloquear o event loop nem manter o pedido aberto esperando escolha humana (FR-001/002/004/005).
- [x] T011 [US1] Implementar em `agente/src/ponte_agente/ponte.py` e `agente/src/ponte_agente/handler.py` o aceite `escolha=<id>` na mesma taskId: emitir WORKING, usar a chave original com `action: accept` e `content.sala`, ecoar token intacto, concluir somente após `complete`, isError ausente ou false e `reservado: true` real, reutilizar o artifact de 003 com política do resource e limpar pending no sucesso; preservar "tipo escolha/recusa; sala escolhida obrigatória na escolha e ausente na recusa" (FR-007/008/009; SC-001).
- [x] T012 [US1] Executar os casos US1 de `agente/tests/test_ponte.py` e conferir nos requests/logs reais método/id, tools/list anterior ao primeiro tools/call, parâmetros originais, chave/token literais, metadata/capability/headers e id de retry diferente; consultar disponibilidade no MCP para provar a reserva e registrar comandos/resultados sem tokens em `specs/004-ponte-a2a-mrtr/quickstart.md` (FR-001 a FR-009/016; SC-001).

**Checkpoint**: A US1 funciona com o MCP real e sem confirmação automática. É um MVP local da ponte, não a entrega completa nem autorização de deploy.

## Phase 4: User Story 2 — corrigir escolha e recusar (Priority: P1)

**Objetivo**: Preservar a pausa em escolha inválida, consumir a recusa no MCP e tornar todos os resultados terminais definitivos.

**Teste independente**: Em negociações separadas com base limpa, enviar escolha=sala-aquario e depois uma alternativa válida; recusar outra Task e comprovar ausência de reserva; provocar erro de tool e falha técnica; dirigir novas mensagens aos três tipos de terminal e comprovar rejeição sem chamada MCP.

### Testes da US2

- [x] T013 [US2] Escrever em `agente/tests/test_ponte.py` os casos de escolha inválida seguida de válida, recusa com `action: decline` real e `complete` sem isError/reservado false/motivo, GetTask após cancelamento e SendMessage em COMPLETED/CANCELED/FAILED; medir ausência de novo tools/call em escolha inválida e terminais, pergunta byte a byte e ausência de reserva após recusa (FR-006/010/012; SC-002/004).
- [x] T014 [US2] Escrever em `agente/tests/test_ponte.py` os casos de isError após retomada com texto exato, inclusive erro contendo reservado false que deve virar FAILED e nunca CANCELED, conflito sem alternativas com `Sem alternativas disponiveis no intervalo`, erro JSON-RPC `-32602` por estado expirado e falha HTTP/rede; usar resultados/relógio controlados apenas nos casos necessários, exigir FAILED sem artifact de sucesso e não expor token em exceções técnicas (FR-004/011; edge cases da spec).

### Implementação da US2

- [x] T015 [P] [US2] Implementar em `agente/src/ponte_agente/ponte.py` a validação da escolha contra as opções recebidas, aplicando "Escolha inválida usa o mesmo pause_text e não chama MCP."; preservar chave, token, pedido, identidade e INPUT_REQUIRED e repetir o texto original sem consumir pending (FR-006; SC-002).
- [x] T016 [P] [US2] Proteger em `agente/src/ponte_agente/tasks.py` e `agente/src/ponte_agente/handler.py` todos os terminais COMPLETED/CANCELED/FAILED antes de transição ou tools/call, retornando o erro suportado pelo SDK sem reabrir registro, alterar histórico/artifacts ou criar outra Task para a continuação (FR-012; SC-004).
- [x] T017 [US2] Implementar em `agente/src/ponte_agente/ponte.py` e `agente/src/ponte_agente/handler.py` `escolha=recusar` como retry do pedido original com mesma chave/token, `action: decline` sem content.sala e WORKING enquanto aguarda HTTP; terminar CANCELED somente após `complete`, sem isError, `reservado: false` e motivo, sem fabricar cancelamento local (FR-010; SC-002).
- [x] T018 [US2] Mapear em `agente/src/ponte_agente/ponte.py` e `agente/src/ponte_agente/handler.py` isError da tool para FAILED com a mensagem original no histórico, verificando isError antes dos campos reservado/sucesso/cancelamento, e erro de protocolo/rede/expiração para FAILED com diagnóstico técnico sem estruturas MCP/token/segredo; não criar artifact de sucesso nem renovar/reconstruir o estado e reutilizar este mapeamento quando não há alternativas (FR-004/011).
- [x] T019 [US2] Centralizar em `agente/src/ponte_agente/tasks.py` a finalização com limpeza de pending em COMPLETED/CANCELED/FAILED, inclusive exceções da retomada, preservando Task pública, histórico e artifacts existentes consultáveis por GetTask; não limpar na escolha inválida ou consulta (FR-003/004/009/010/011/012).
- [x] T020 [US2] Executar os casos US2 de `agente/tests/test_ponte.py`, comprovar por consultas MCP os efeitos de aceite/recusa e por contagem de requests a rejeição de terminais/escolhas inválidas; registrar evidências sem estado privado em `specs/004-ponte-a2a-mrtr/quickstart.md` (FR-006/010/011/012; SC-002/004).

**Checkpoint**: Escolhas inválidas não consomem a negociação; recusa e falhas refletem o MCP; todos os terminais permanecem definitivos.

## Phase 5: User Story 3 — negociações independentes e rastreáveis (Priority: P2)

**Objetivo**: Retomar duas Tasks em ordem inversa, preservar o trace original e produzir perguntas determinísticas sem estado compartilhado indevido.

**Teste independente**: Pausar uma Task de sala-fusca (16:00–17:00, Jennifer) e outra de sala-garagem (14:00–15:00, Marty) em 2026-11-03 (-03:00), cada uma com trace-id próprio; retomar em ordem inversa escolhendo sala-mirante em ambas. Verificar reservas, identidades, token/chave/pedido e trace exclusivos por Task. Em cenário limpo separado, comparar dois pedidos iguais que apenas pausam.

### Testes da US3

- [x] T021 [US3] Escrever em `agente/tests/test_ponte.py` o cenário HTTP de duas Tasks simultaneamente pausadas e retomadas em ordem inversa, com intervalos/responsáveis/traces distintos e sala-mirante nos dois aceites; associar cada requestState e chave reais à sua Task pela captura privada e verificar reservas/consultas finais sem trocar dados e sem forçar corrida de escrita no mesmo intervalo (FR-003/013; SC-003).
- [x] T022 [US3] Escrever em `agente/tests/test_ponte.py` casos de dois pedidos iguais que só pausam (textos idênticos, Task/contextId próprios) e de retomadas com header ausente ou com outro trace-id, mais Task criada sem traceparent; conferir o trace-id original por Task em todos os requests MCP, sem herança de outra Task e com ids iniciais/retry diferentes (FR-014/015/016; SC-005).

### Implementação da US3

- [x] T023 [P] [US3] Ajustar `agente/src/ponte_agente/handler.py` para capturar o trace original na criação do TaskRecord, buscar cada continuação exclusivamente por taskId e passar o contexto desse registro ao host, mesmo sem header na retomada ou com header posterior diferente; não usar contextId como chave nem variável de última negociação (FR-003/013/015).
- [x] T024 [P] [US3] Ajustar `agente/src/ponte_agente/mcp_host.py` para cumprir "traceparent_original pertence à Task e é passado explicitamente ao host em cada chamada."; construir meta por request sem mutar defaults do cliente reutilizável, preservar o trace-id na descoberta/resource/call/retry associados à Task e os headers espelhados pelo SDK, sem inferir capabilities/contexto da conexão (FR-015/016; SC-005).
- [x] T025 [US3] Ampliar em `agente/tests/test_ponte.py` a verificação de privacidade usando todos os tokens efetivamente emitidos no cenário e tokens sentinela nos casos controlados; examinar card, respostas SendMessage/GetTask, mensagens, history, metadata, artifacts e erros, incluindo pausa inválida, cancelamento, falha e duas Tasks, recusando qualquer token ou campo requestState e verificando limpeza interna após terminais (FR-004/013; SC-004).
- [x] T026 [US3] Adicionar em `agente/tests/test_ponte.py` integração de pausa → reinício apenas do MCP com a mesma chave/audience → retomada pela Task preservada antes da expiração → reserva real; não abrir o token, reiniciar o agente ou publicar a chave/token; verificar que o host restabelece HTTP sem perder parâmetros, identidade e trace-id (FR-003/004/007/015/016; princípio III; edge case de restart).
- [x] T027 [US3] Executar os casos US3 e a suíte inteira de `agente/tests/test_ponte.py`, comparar alternativas byte a byte e cruzar logs/requests/consultas de ambas as Tasks; registrar evidências de isolamento, ausência de vazamento, restart e trace-id sem tokens em `specs/004-ponte-a2a-mrtr/quickstart.md` (FR-013/014/015/016; SC-003/004/005).

**Checkpoint**: As três histórias funcionam na mesma aplicação e cada continuação pertence somente à sua Task.

## Phase 6: Polish — regressão e conformidade transversal

**Objetivo**: Consolidar evidências da implementação sem antecipar publicação/entrega da feature 005.

- [x] T028 Executar `python -m unittest discover -s agente/tests -v`, incluindo os casos diretos de 003 e `agente/tests/test_ponte.py`; revisar `agente/src/ponte_agente/{handler.py,mcp_host.py,tasks.py,ponte.py}` contra os cinco princípios, verificar arquivos protegidos inalterados e ausência de novos pacotes/LLM/regras de domínio no agente e registrar resultados em `specs/004-ponte-a2a-mrtr/quickstart.md` (FR-001 a FR-016; princípios I–V).
- [x] T029 Reiniciar os dois processos após os testes e executar com Python 3.10+ `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` sem modificar `validador/validar.py`; exigir 36 PASS e saída 0 e registrar a saída completa e os comandos em `specs/004-ponte-a2a-mrtr/quickstart.md`, tratando qualquer falha como bloqueio de conclusão da feature (princípio V).
- [x] T030 Atualizar `specs/004-ponte-a2a-mrtr/quickstart.md` com comandos reproduzíveis de pausa/GetTask/aceite/recusa/erro, reinícios que preservam dados iniciais, verificações manuais restantes herdadas de 002 (integridade, expiração, argumentos adulterados e capability ausente) e evidências de descoberta/trace/id novo; diferenciar execução real de casos controlados e remover tokens/segredos das evidências compartilháveis (FR-004/016; princípios III/V).
- [x] T031 Documentar em `specs/004-ponte-a2a-mrtr/quickstart.md` os caminhos/linhas reais onde pausa e retry acontecem, a guarda/limpeza por Task e qualquer limitação de SDK com evidência sanitizada; encaminhar à feature 005 a consolidação do README nas quatro seções exigidas, a saída integral mais recente, clone limpo e entrega do fork público na main, sem declarar esses gates cumpridos nesta etapa (princípios I–V).

## Dependências e ordem de execução

```text
001 MCP → 002 MRTR seguro → 003 host MCP/A2A direto
  → Setup T001–T002 → Fundação T003–T004
  → US1 T005–T012 → US2 T013–T020 → US3 T021–T027
  → Polish T028–T031 → 005 conformidade/entrega
```

- T001 bloqueia todo incremento se 001–003 não estiverem prontas; T002 depende desse gate. T003 precede T004.
- US1: T005 → T006; depois T007 e T008 podem correr juntas. T009 → T010 → T011 dependem dos componentes anteriores; T012 exige a implementação completa da história.
- US2 depende de US1 para existir pausa/aceite real. T013 → T014; depois T015 e T016 podem correr juntas; T017 → T018 → T019 → T020 seguem sequencialmente.
- US3 depende de US1/US2; T021 → T022; depois T023 e T024 podem correr juntas. T025 → T026 → T027 são sequenciais para não editar o mesmo teste em paralelo.
- T028 → T029 → T030 → T031 são sequenciais; reiniciar processos entre a suíte e o validador para não reutilizar reservas criadas por testes.
- Cada história tem um cenário executável separadamente sobre a base já concluída. A independência de verificação não elimina a dependência incremental real de pausa/retomada; não iniciar histórias inteiras em paralelo.

## Exemplos de execução paralela por história

Os exemplos indicam oportunidades para implementação futura; não despacham agentes durante a geração/análise.

| História | Pré-requisito | Trabalho simultâneo permitido | Por que não conflita |
| --- | --- | --- | --- |
| US1 | T001–T006 concluídas e falhas esperadas demonstradas | T007 (`ponte.py`) + T008 (`mcp_host.py`) | Tradutor e API do host são arquivos distintos; ambos seguem o contrato já definido. |
| US2 | US1 e T013–T014 concluídas | T015 (`ponte.py`) + T016 (`tasks.py`, `handler.py`) | Validação de opção e guarda de terminais não dependem uma da outra. |
| US3 | US2 e T021–T022 concluídas | T023 (`handler.py`) + T024 (`mcp_host.py`) | Contexto explícito já existe no TaskRecord; cada tarefa altera um lado do contrato do host. |

## Estratégia de implementação

1. Validar 001–003, preparar o harness e separar os registros privados da Task pública.
2. Entregar o MVP US1: pausa consultável, escolha explícita, novo tools/call e artifact real; executar seu teste independente.
3. Acrescentar US2: invalid choice, recusa MCP, falhas e terminais; executar os testes das duas histórias.
4. Acrescentar US3: isolamento, determinismo, contexto de trace e prova de opacidade/restart; executar a suíte completa.
5. Cumprir T028–T031 e encaminhar evidências à 005. Nenhuma fase exige deploy, streaming, banco, autenticação ou continuidade entre Tasks.

## Cobertura rastreável

| Requisito/critério | Tarefas de implementação/verificação |
| --- | --- |
| FR-001 | T005–T008, T010, T012 |
| FR-002 | T005, T007, T010, T012 |
| FR-003 | T003, T005, T009, T019, T021, T023, T026 |
| FR-004 | T003–T005, T007, T009–T010, T014, T018–T019, T025–T026, T030 |
| FR-005 | T004, T006, T009–T010, T012 |
| FR-006 | T013, T015, T020 |
| FR-007 | T006, T008, T011–T012, T026 |
| FR-008 | T006, T008, T011–T012 |
| FR-009 | T004, T006, T011–T012, T019 |
| FR-010 | T013, T017, T019–T020 |
| FR-011 | T014, T018–T020 |
| FR-012 | T013, T016, T019–T020 |
| FR-013 | T003, T021, T023, T025, T027 |
| FR-014 | T022, T027 |
| FR-015 | T003, T022–T024, T026–T027 |
| FR-016 | T001–T002, T004, T006, T008, T012, T022, T024, T026–T030 |
| SC-001 | T006, T011–T012 |
| SC-002 | T013, T015, T017, T020 |
| SC-003 | T021, T027 |
| SC-004 | T013, T016, T025, T027 |
| SC-005 | T022–T024, T027 |

As tarefas de setup/fundação/polish também cobrem os gates constitucionais citados. Os testes de segurança do servidor pertencem a 002, e os gates finais de documentação/clone/fork a 005; suas evidências permanecem obrigatórias para declarar a entrega completa. A cobertura é planejada, não prova de implementação aprovada.
