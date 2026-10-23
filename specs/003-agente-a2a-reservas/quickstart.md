# Quickstart: Agente A2A para descoberta e reservas diretas

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

## Instalação e dois terminais

Após implementar 001 e 003, com Python 3.12+ disponível como python3.12.
A sequência recomendada inclui 002 antes de 003, mas MRTR não é necessário
para estes cenários de reserva livre:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./servidor-mcp -e ./agente
export REQUEST_STATE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp
```

Em outro terminal, na raiz:

```bash
. .venv/bin/activate
python -m ponte_agente
```

O agente usa MCP_URL padrão; o segredo não é configuração do host MCP do agente.

## Descoberta e reserva livre

```bash
curl -sS http://127.0.0.1:7300/.well-known/agent-card.json
curl -sS http://127.0.0.1:7300/a2a   -H 'Content-Type: application/json'   -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'   --data-binary '{"jsonrpc":"2.0","id":"direta-1","method":"SendMessage","params":{"message":{"messageId":"direta-msg-1","role":"ROLE_USER","parts":[{"text":"reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc"}]}}}'
```

Esperado: card v1 e Task COMPLETED com artifact reserva e politica 2026-11-01.
Capture o id retornado e use-o em params.id de GetTask; não copie o id dos exemplos.
Repita o mesmo cenário em bases reiniciadas para testar sem A2A-Version e com
A2A-Version: 1.0. Versão explícita incompatível deve ser recusada.

### Evidências executadas (US1 — T017)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_tasks.py' -v` → `Ran 4 tests in 0.003s — OK`
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_agente_direto.py' -v` → `Ran 2 tests in 2.128s — OK`
- **Descoberta pública e reserva direta**:
  - `GET /.well-known/agent-card.json` retornou HTTP 200 com `supportedInterfaces` (`url`: `<base>/a2a`, `protocolBinding`: `JSONRPC`, `protocolVersion`: `1.0`), `capabilities` (`streaming: false`, `pushNotifications: false`, `extendedAgentCard: false`) e skill `reservar-sala`.
  - `POST /a2a` (`SendMessage` para `sala-porao` em `2026-11-03T09:00:00-03:00` a `2026-11-03T10:00:00-03:00`, `responsavel=Doc`) criou Task com `id` e `contextId` UUID próprios (não fixados), transitou por `TASK_STATE_SUBMITTED` → `TASK_STATE_WORKING` → `TASK_STATE_COMPLETED` e produziu `artifact` `reserva` com JSON textual contendo `reserva`, `sala`, `inicio`, `fim`, `responsavel` e `politica: "2026-11-01"` lida do resource `politica://uso`.
  - Testado em processos reiniciados sem header `A2A-Version` e com `A2A-Version: 1.0`; versões explícitas incompatíveis (`0.3`, `2.0`, `invalid`) foram recusadas com erro JSON-RPC.
  - Consulta subsequente ao servidor MCP via `consultar_disponibilidade` confirmou `livre: false` para o intervalo reservado.
  - **Distinção de escopo**: Gate FR-008 permanece pendente/reprovado devido ao anúncio adicional `url` em `mcp==2.3.0`; a aceitação final das 36 verificações oficiais depende da conclusão das specs `004` e `005`.

### Evidências executadas (US2 — T024)

- **Comandos executados (regressão US1 + US2)**:
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_tasks.py' -v` → `Ran 7 tests in 0.005s — OK`
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_agente_direto.py' -v` → `Ran 4 tests in 4.587s — OK`
- **Identidade e consulta em `GetTask`**:
  - `GetTask` para Task concluída retornou diretamente o objeto `Task` no `result` (aceitando formato direto da implementação oficial v1.0) com o mesmo `id`, `contextId`, `status.state: "TASK_STATE_COMPLETED"`, `history` e `artifacts[0].name == "reserva"`, sem mutar o registro em memória.
  - `GetTask` para `id` desconhecido retornou erro JSON-RPC oficial `TaskNotFoundError` (`code: -32001`).
- **Consulta durante `TASK_STATE_WORKING`**:
  - Com `tools/call` retido por barreira HTTP controlada (`TransparentMCPObserverProxy`), uma requisição `GetTask` concorrente sobre `/a2a` observou a Task em `TASK_STATE_WORKING` com `id`, `contextId`, `history` contendo a mensagem `ROLE_USER` e sem artifacts; após liberar a barreira, `SendMessage` concluiu em `TASK_STATE_COMPLETED`.
- **Mensagens exatas de domínio e ausência de artifact em falhas**:
  - `sala-delorean` inexistente e toda a matriz de erros de política (`Sala inexistente: sala-delorean`, `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`, `Duracao acima do limite: a politica permite no maximo 2 horas`, `Intervalo invalido: fim deve ser posterior a inicio`, `Sem alternativas disponiveis no intervalo`) transitaram para `TASK_STATE_FAILED` preservando o texto retornado pela tool no histórico e em `status.message`, sem qualquer `artifact`.
- **Terminalidade imutável e falhas técnicas sem vazamento**:
  - `SendMessage` referenciando `taskId` em estado terminal (`COMPLETED`, `FAILED` e preventivamente `CANCELED`) foi recusado antes de qualquer nova chamada HTTP MCP e sem alterar histórico, estado ou artifacts da Task.
  - Falha técnica/protocolo simulada após criação da Task encerrou a Task em `TASK_STATE_FAILED` com a mensagem pública `Falha ao executar pedido no servidor MCP`, sem `artifact` e sem expor exceção bruta ou `requestState`.

### Evidências executadas (US3 — T032)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_mcp_host.py' -v` → `Ran 8 tests in 0.274s — FAILED (failures=1)` (7 aprovados; 1 falha esperada no gate estrito `test_gate_fr008_capabilities_forma_exata`)
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_agente_direto.py' -v` → `Ran 5 tests in 5.827s — OK`
- **Descoberta explícita e leitura de resource antes do primeiro `tools/call`**:
  - Captura HTTP real (`TransparentMCPObserverProxy` e `ObservingMCPHTTPServer`) comprovou a sequência exata `tools/list` (incluindo paginação via `nextCursor` quando presente) → `resources/read` (`politica://uso`) → `tools/call` (`reservar_sala`).
  - Quando `reservar_sala` está ausente no catálogo descoberto, `MCPDiscoveryError` interrompe a operação sem fallback local e sem enviar `tools/call`.
  - Com fixture controlada de `politica://uso` retornando `versao: 2027-08-15-fixture` na primeira linha e `tools/call` retornando valor divergente, o artifact `reserva` gravou `"politica": "2027-08-15-fixture"`, provando que a versão provém exclusivamente da primeira linha do resource.
- **Headers espelhados, `_meta` por request, `trace-id` no stderr e ausência de herança**:
  - Todos os requests HTTP MCP emitidos pelo agente continham `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method` correspondente ao método JSON-RPC e `Mcp-Name` em `resources/read` (`politica://uso`) e `tools/call` (`reservar_sala`), além de `_meta` com `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities`.
  - Três Tasks independentes enviadas ao mesmo processo do agente com `traceparent` A (`4bf92f3577b34da6a3ce929d0e0e4736`), `traceparent` B (`99999999999999999999999999999999`) e sem `traceparent` comprovaram no wire HTTP e no `stderr` do `ponte_mcp` (`[ponte_mcp] method=... id=... traceparent=...`) que todas as operações de cada Task preservam seu `trace-id` original e que a Task sem header não herda `traceparent` anterior.
- **Fronteira `input_required` (FR-015) e resultado de T031**:
  - `InputRequiredResult` com marcador opaco `v1.OPAQUE_SENTINEL_MARKER_NOT_BASE64_!@#$%^&*()` foi recebido cru sem acionar o callback defensivo, sem retry automático e sem expor o marcador em `Task` ou `AgentCard`.
  - **Limitações para o README da 005 (sem tratar como PASS)**:
    1. **Gate FR-008 (`mcp==2.3.0`)**: O SDK oficial `mcp==2.3.0` anuncia `{"elicitation": {"form": {}, "url": {}}}` sempre que `elicitation_callback` é registrado, sem API pública para omitir `url`. O gate `test_gate_fr008_capabilities_forma_exata` permanece **FAIL** (não mascarado).
    2. **Perfil A2A v1 sem `A2A-Version`**: O starter e o validador enviam métodos v1.0 sem o header `A2A-Version`; `StarterProfileContextBuilder` aplica `1.0` apenas quando o header está ausente em `/a2a`, preservando e validando qualquer header explícito.

## Testes previstos

```bash
python -m unittest discover -s agente/tests -p 'test_*.py' -v
```

Cobrir GetTask, terminalidade, erro sala-delorean, origem da política, descoberta
anterior ao tools/call, metadados/headers e rastreamento. O stderr MCP deve conter
4bf92f3577b34da6a3ce929d0e0e4736, sem exigir span-id igual.

A bateria inclui `test_agente_direto.py` (dois processos/HTTP),
`test_mcp_host.py` (sessão raw, descoberta e wire) e `test_tasks.py`
(parser/identidade/transições). Parar os processos dos terminais antes da bateria
se os testes precisarem usar as portas padrão; cada cenário controla seus próprios
subprocessos e limpa o estado.

### Execução da bateria completa e ambiente virtual novo (Phase 6 — T033/T034)

- **Regressão de startup, `cwd`, overrides e manifesto (`T033`)**:
  - `.venv/bin/python -m unittest discover -s agente/tests -p 'test_agente_direto.py' -v` → `Ran 7 tests in 6.757s — OK`
  - O agente iniciou a partir de um diretório temporário vazio (`cwd` sem `dados/`), sem `REQUEST_STATE_SECRET` no ambiente e com override `A2A_BASE_URL=https://salas.hillvalley.example:8443`, refletindo `https://salas.hillvalley.example:8443/a2a` no Agent Card, concluindo reserva via HTTP no MCP e encerrando de forma limpa.
  - Verificação estática do código-fonte de `agente/src/ponte_agente/*.py` confirmou ausência de referências a `ponte_mcp`, `salas.json`, `reservas.json`, `politica-de-uso.md` ou `REQUEST_STATE_SECRET`.
- **Reprodução em ambiente virtual novo (`T034`)**:
  - Ambiente virtual criado do zero com `python3.12 -m venv` e instalação `python -m pip install -e ./servidor-mcp -e ./agente`.
  - Geração e exportação segura do segredo exclusivamente para o processo MCP (`export REQUEST_STATE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"`), seguida de `unset REQUEST_STATE_SECRET` antes de subir `python -m ponte_agente`.
  - Comandos `curl` executados contra os processos nas portas padrão `7300` e `7301`:
    - `GET http://127.0.0.1:7300/.well-known/agent-card.json` → HTTP 200 com `supportedInterfaces[0]` (`url: "http://127.0.0.1:7300/a2a"`, `protocolBinding: "JSONRPC"`, `protocolVersion: "1.0"`) e skill `reservar-sala`.
    - `POST http://127.0.0.1:7300/a2a` (`SendMessage` com `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`) → HTTP 200, `result.task.status.state == "TASK_STATE_COMPLETED"` e `artifact` `reserva` com `"reserva": "res-0003"`, `"sala": "sala-porao"`, `"politica": "2026-11-01"`.
    - `POST http://127.0.0.1:7300/a2a` (`GetTask` usando o `id` retornado pela Task) → HTTP 200, mesmo `id` e `contextId`, `TASK_STATE_COMPLETED` e `artifacts`.
    - `stderr` do `ponte_mcp`:
      ```text
      StreamableHTTP session manager started
      [mcp] method=tools/list id=1 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-c12747416cdb3740-01
      [mcp] method=resources/read id=2 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-ae52e1aa3b18b8bd-01
      [mcp] method=tools/call id=3 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-753372b31629f658-01
      ```
  - Bateria completa `python -m unittest discover -s agente/tests -p 'test_*.py' -v` no venv novo: `Ran 22 tests in 7.098s — FAILED (failures=1)` (21 testes aprovados; 1 falha estrita esperada em `test_gate_fr008_capabilities_forma_exata`).
  - Bateria de regressão do servidor MCP (`python -m unittest discover -s servidor-mcp/tests -p 'test_*.py' -v`): `Ran 45 tests in 13.554s — OK`.

### Auditoria dos cinco princípios constitucionais e arquivos protegidos (T035)

- `git diff --stat dados/ validador/ exemplos/ README.md` → vazio (nenhum arquivo protegido alterado, movido ou reescrito; `README.md` da raiz preservado para a spec `005`).
- **Princípio I (Fronteiras e responsabilidade)**: `ponte_mcp` e `ponte_agente` executam em processos separados comunicando-se exclusivamente por HTTP (`MCP_URL`); toda regra de sala, janela, duração, conflito e alternativas reside no servidor MCP.
- **Princípio II (Estado explícito) — Gate FR-008 REPROVADO**: Cada operação MCP envia `_meta` e cabeçalhos espelhados explícitos e cada Task possui `id`/`contextId`/`trace` próprios sem herança entre requests; contudo, o pin `mcp==2.3.0` anuncia `{"elicitation": {"form": {}, "url": {}}}` no wire, mantendo o gate estrito FR-008 reprovado até solução compatível por API pública.
- **Princípio III (Integridade e opacidade)**: O agente não recebe `REQUEST_STATE_SECRET`, não decodifica nem altera `requestState`, e mantém `InputRequiredResult` cru isolado dos serializers públicos.
- **Princípio IV (Contratos e determinismo)**: Gramática fixa determinística sem LLM, pins exatos em `agente/pyproject.toml`, ausência de extras fora do escopo (`all`, `telemetry`, `sqlalchemy`, `fastapi`), e preservação exata das mensagens de domínio.
- **Princípio V (Conformidade e rastreio)**: Descoberta `tools/list` antes do primeiro `tools/call`, versão da política lida da primeira linha de `politica://uso`, propagação do `trace-id` original para todos os requests MCP da Task e registro em `stderr`.

### Cobertura FR-001–015 / SC-001–005 e correspondência com o validador (T036)

| Requisito / Critério | Status na spec 003 | Evidência principal |
| --- | --- | --- |
| FR-001, FR-002, FR-003 | Atendido | `app.py`, ` __main__.py`, `test_agente_direto.py` (processos independentes, card v1.0, `/a2a` JSON-RPC, `StarterProfileContextBuilder`) |
| FR-004, FR-005 | Atendido | `tasks.py`, `handler.py`, `test_tasks.py` (UUIDs `id`/`contextId` próprios, `SUBMITTED` → `WORKING`, gramática fixa sem LLM) |
| FR-006, FR-007, FR-009, FR-010 | Atendido | `mcp_host.py`, `test_mcp_host.py`, `test_agente_direto.py` (`tools/list` paginado antes de `tools/call`, `politica://uso`, headers espelhados, `traceparent` por Task sem herança) |
| FR-008 | **BLOQUEADO / FAIL** | `test_gate_fr008_capabilities_forma_exata` reprova o anúncio adicional `url` de `mcp==2.3.0` (`{'elicitation': {'form': {}, 'url': {}}}`) |
| FR-011, FR-012, FR-013, FR-014 | Atendido (escopo direto) | `tasks.py`, `handler.py`, `test_tasks.py`, `test_agente_direto.py` (`COMPLETED` com artifact `reserva`, `FAILED` com mensagem exata da tool, `GetTask` direto inclusive em `WORKING`, guarda terminal) |
| FR-015 | Atendido | Fronteira `003`/`004` preservada: `InputRequiredResult` cru sem callback automático, sem falso terminal e sem exposição de `requestState` |
| SC-001, SC-002, SC-003, SC-004, SC-005 | Atendido | Comprovados em `test_tasks.py`, `test_mcp_host.py` e `test_agente_direto.py` |

- **Correspondência com as verificações oficiais de `validador/validar.py`**:
  - **Cobertas por esta feature (`003`)**: verificações `21`, `22`, `23` (Agent Card, interface JSON-RPC 1.0 e skill `reservar-sala`), `24`, `25` (`SendMessage` em sala livre concluindo em `TASK_STATE_COMPLETED` com artifact `reserva` e versão da política), `26` (`GetTask` retornando `id`, `contextId` e estado corrente), `35` (sala inexistente `sala-delorean` terminando em `TASK_STATE_FAILED` com a mensagem da tool) e a guarda terminal parcial da `31` (rejeição de `SendMessage` em Task terminal).
  - **Reservadas para integração na spec `004`**: verificações `27`, `28`, `29`, `30`, `31` (após retomada de pausa), `32`, `33`, `34` e `36` (pausa `TASK_STATE_INPUT_REQUIRED`, lista de alternativas, escolha fora do enum, continuação com `requestState`, recusa `TASK_STATE_CANCELED`, duas Tasks pausadas simultâneas, não exposição de `requestState` em respostas de conflito e determinismo da pausa).
  - **Declaração de entrega (`005`)**: A entrega integral do desafio só pode ser declarada após concluir as specs `004` e `005`, executar `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` com **36/36 verificações aprovadas e código de saída 0**, validar os critérios manuais, substituir o `README.md` final pelas quatro seções exigidas em clone limpo e disponibilizar o link público na branch `main`.

## Gate de capabilities MCP

FR-008 exige `{"elicitation": {"form": {}}}` em cada request. A pesquisa do pin
MCP 2.3.0 identificou anúncio adicional url; essa divergência mantém o gate
reprovado, mesmo quando a reserva livre funcionar. T005/T006/T031 exigem observar
o wire real, buscar solução por API pública compatível e registrar evidência.
Não relaxar a asserção, modificar atributos privados ou declarar PASS por haver
somente suporte a form. A limitação e seu resultado real devem chegar ao README
da 005, sem apresentar documentação como substituta de conformidade.

## Critérios de passagem para 004/005

As chamadas diretas alteram reservas. Reinicie ambos antes de outra bateria.
Os testes de pausa não são critério de conclusão desta etapa isolada; seguir
para 004 e só então exigir a validação oficial integral.

Na 005, reiniciar ambos os processos e executar o validador original completo;
exigir 36/36 e saída 0, critérios manuais, README nas quatro seções exigidas,
comandos verificados em clone limpo e link do fork público em main. O validador
não tem filtro parcial; os testes desta feature não comprovam a entrega integral.
