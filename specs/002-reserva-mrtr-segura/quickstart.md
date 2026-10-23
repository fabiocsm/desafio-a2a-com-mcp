# Quickstart: Reserva com alternativas e retomada MRTR segura

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

## Preparação e startup

Concluir e validar a base `001-servidor-mcp-salas` (Python >= 3.12 e pins travados `mcp==2.3.0`, `starlette==0.48.0`, `uvicorn==0.31.1`, `sse-starlette==3.0.3`, `pydantic==2.12.0`). Em cada terminal utilizado, ative a `.venv` da raiz do repositório.

Para gerar e exportar a chave de integridade (>= 32 bytes de aleatoriedade em hexadecimal) sem registrar nem imprimir seu valor:

```bash
. .venv/bin/activate
python -m pip install -e ./servidor-mcp
export REQUEST_STATE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp
```

Conserve a mesma variável `REQUEST_STATE_SECRET` no terminal do servidor ao interromper e reiniciar o processo. Não gere outra chave entre a emissão da pergunta (`input_required`) e o retry (`tools/call` com `inputResponses` e `requestState`). A execução integral do validador (`python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`) com as 36 verificações e os dois processos recém-iniciados pertence à spec `005`.

## Emitir uma negociação real

No segundo terminal, usando a raiz do repositório:

```bash
. .venv/bin/activate
python -c 'import json; print(json.dumps(json.load(open("exemplos/wire/03-tools-call-conflito-input-required.json"))["request"]["body"]))' |
curl -sS http://127.0.0.1:7301/mcp   -H 'Content-Type: application/json'   -H 'Accept: application/json, text/event-stream'   -H 'MCP-Protocol-Version: 2026-07-28'   -H 'Mcp-Method: tools/call'   -H 'Mcp-Name: reservar_sala'   --data-binary @-
```

Esperado: input_required, uma chave em inputRequests, opções sala-fusca e
sala-mirante e token não vazio. Nunca use o token ilustrativo do exemplo 04.

## Bateria de retomada

```bash
python -m unittest discover -s servidor-mcp/tests -p 'test_mrtr.py' -v
```

O teste de subprocesso deve emitir pergunta, preservar chave/token/argumentos,
parar o MCP, iniciá-lo com o mesmo segredo/nome e enviar novo request antes de
600s. Esperado: reserva na alternativa, sem recuperação de memória de continuação.

Em cenários separados, testar token adulterado, expirado, argumentos divergentes,
form ausente, elicitation genérica e url-only. Esperado: -32602 nos três primeiros
e -32021/HTTP 400 para ausência de form. Use relógio controlado no teste de expiração,
mantendo o TTL de produção em 600s. Testar decline e cancel sem criação de reserva.

Executar todas as linhas da matriz de aceite de segurança/continuação em
[spec.md](spec.md): alteração/truncamento do token, expiração antes/depois de
restart, cada argumento divergente, campos de retry incompletos, mapa vazio,
chave divergente/entrada adicional e payload incompatível por fixture interna.
Rejeições de protocolo devem ser -32602, sem mutação nem fallback para pedido
inicial. O controle de relógio fica no processo de testes (inclusive no worker
de teste usado para expiração após restart), nunca em endpoint de produção.

Gerar também uma pergunta, ocupar a alternativa por outra reserva válida e então
confirmá-la: esperado complete/isError: true, sem nova pergunta e sem sobreposição;
não comparar texto específico para esse erro adicional.

Reiniciar a base entre cenários que escrevem reservas; para restart com estado
pendente, reiniciar somente o MCP mantendo a chave. Conferir ids diferentes nos logs.
Detalhes: [modelo](data-model.md) e [contrato](contracts/mrtr.md).

## Evidências executadas — US1 (T015)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_salas.py' -v` (`Ran 16 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mrtr.py' -v` (`Ran 5 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -v` (`Ran 40 tests ... OK`, incluindo regressão completa da `001`)
- **Resultados verificados**:
  - Seleção de alternativas livres com capacidade >= solicitada, ordenação por `(capacidade, id)` e corte em no máximo três opções, inclusive em fixtures sintéticas em memória sem alterar `dados/`.
  - Emissão `input_required` no cenário original (`sala-garagem`, `2026-11-03T14:00:00-03:00` a `15:00:00-03:00`, `Marty`) com uma única entrada `elicitation/create` em `mode: form`, `requestedSchema` plano e `enum: ["sala-fusca", "sala-mirante"]`, sem gravar reserva na emissão.
  - Retomada `accept` (`sala-fusca`) com id JSON-RPC novo (`4 != 3`), chave capturada e `requestState` ecoado literalmente, concluindo com `resultType: complete`, `isError: false`, equivalência entre `structuredContent` e `content[].text` e reserva visível na consulta posterior.
  - Conflito sem alternativas (`sala-mirante` ocupada) retorna `complete` com `isError: true` e `Sem alternativas disponiveis no intervalo`, sem elicitation.
  - Escolha fora do schema e alternativa ocupada entre a oferta e o `accept` não produzem reserva sobreposta; a ocupação pós-oferta encerra em `complete` com `isError: true` sem nova pergunta.
  - `stderr` conferido com `tools/list` antes do primeiro `tools/call`, registro de `method`, `id` e `traceparent` corrente na chamada inicial e no retry com ids distintos, sem expor token ou `REQUEST_STATE_SECRET`.

## Evidências executadas — US2 (T020)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mrtr.py' -v` (`Ran 8 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_*.py' -v` (`Ran 43 tests in 12.492s ... OK`, incluindo `TestStartupEConfiguracaoT032` de `test_mcp_http.py` e toda a regressão US1/001)
- **Resultados verificados**:
  - **Configuração de segredo (`TestStartupEConfiguracaoT032`)**: startup sem `REQUEST_STATE_SECRET`, com hexadecimal inválido e com menos de 32 bytes rejeitado imediatamente sem expor segredo em `stdout`/`stderr`; startup com segredo válido (>= 32 bytes) em `cwd` alternativo funciona normalmente.
  - **Integridade do token (`T016`)**: alteração de 1 caractere nos bytes protegidos (`v1.<b64u>`) e truncamento do token em casos separados rejeitados pelo `RequestStateBoundary` com HTTP `400` e JSON-RPC `-32602`, sem gravação de reserva.
  - **Expiração em 600s (`T016`)**: com `DEFAULT_STATE_TTL = 600` mantido em produção e `unittest.mock.patch("mcp.server.request_state.time.time")` no relógio efetivo do SDK, o retry em `t0 + 599s` é aceito e o retry em `t0 + 601s` é rejeitado com `-32602` / HTTP `400`, sem renovar o prazo.
  - **Vinculação de argumentos (`T016`)**: adulteração separada de `sala`, `inicio`, `fim` e `responsavel` no retry rejeitada com `-32602` / HTTP `400` pelo digest SHA-256 canônico dos argumentos na `RequestStateBoundary`, mantendo tanto o intervalo original quanto o horário adulterado livres.
  - **Continuação incompleta e correlação inválida (`T016`)**: omissão isolada de `requestState` (inclusive apontando para sala livre para provar ausência de fallback para chamada inicial) ou de `inputResponses`, mapa `inputResponses` vazio, chave divergente e entrada adicional rejeitados com `-32602` / HTTP `400`, sem mutação de estado.
  - **Payload interno incompatível (`T016`, `T018`)**: tokens selados com a mesma chave mas `schema_version != 1`, `tool_name != "reservar_sala"` ou campo obrigatório ausente (`candidatas` ou `argumentos`) rejeitados na reconstrução com `-32602` / HTTP `400`, sem virar `-32603` nem `complete`/`isError: true`.
  - **Restart real de subprocesso (`T017`)**: negociação emitida na instância 1 (`id=3`), processo encerrado, instância 2 iniciada com outro `REQUEST_STATE_SECRET` rejeita o retry (`-32602`), instância 3 iniciada com o mesmo `REQUEST_STATE_SECRET` e nome aceita o retry (`id=5 != 3`) antes de 600s e conclui a reserva em `sala-fusca` sem store/sessão de continuação; instância 4 iniciada após `t0 + 601s` (via relógio controlado apenas no harness de teste) mantém a expiração original (`-32602`).

## Evidências executadas — US3 (T026)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mrtr.py' -v` (`Ran 10 tests in 6.046s ... OK`)
- **Resultados verificados**:
  - **Matriz de `clientCapabilities` por chamada (`T021`)**:
    - Conflito com alternativas e `clientCapabilities: {"elicitation": {"form": {}}}` retorna HTTP `200` e `resultType: "input_required"`.
    - Logo após chamada com `form`, envio de `clientCapabilities: {}` (incluindo o `request.body` extraído de `exemplos/wire/06-erro-32021-sem-elicitation.json`), `{"elicitation": {}}` e `{"elicitation": {"url": {}}}` é rejeitado com HTTP `400`, código `-32021` e `data.requiredCapabilities: {"elicitation": {"form": {}}}` sem herdar capability da chamada anterior e sem mutar reservas.
    - Omissão de `io.modelcontextprotocol/clientCapabilities` em `_meta` permanece distinguida com `-32602` / HTTP `400` (regra herdada da `001`).
    - Reserva em sala livre (`sala-aquario` 09h–10h) e conflito sem alternativas disponíveis (`sala-mirante` ocupada 11h–12h) não exigem `elicitation.form` desnecessariamente, concluindo com `complete` (`reservado: true` e `isError: true` respectivamente) mesmo quando `clientCapabilities: {}`.
  - **Recusa (`decline`) e cancelamento (`cancel`) sem mutação (`T022`)**:
    - Em negociações reais independentes (incluindo os argumentos de `exemplos/wire/11-tools-call-retry-recusa.json`), o retry com `id` novo, chave capturada e `requestState` ecoado literalmente para `action: "decline"` e `action: "cancel"` conclui com HTTP `200`, `resultType: "complete"`, `isError: false`, `structuredContent.reservado: false`, `motivo` preenchido (`"recusado"` / `"cancelado"`), equivalência entre `content[0].text` e `structuredContent`, e preservação integral das reservas existentes antes/depois (no escopo puramente MCP; a tradução de `escolha=recusar` para `TASK_STATE_CANCELED` pertence à spec `004`).
  - **Candidato único (`T022`)**:
    - Após ocupar `sala-fusca` das 14h às 15h via reserva válida, o conflito em `sala-garagem` 14h–15h oferece unicamente `["sala-mirante"]` no schema (`enum`), rejeita tentativa de aceitar `sala-fusca` ou `sala-aquario` sem gravar reserva e conclui normalmente ao aceitar `sala-mirante`.

## Regressão integral, reprodução em `.venv` nova e auditoria (T027–T029)

- **Suíte integral (`T027`)**:
  - Comando: `.venv/bin/python -m unittest discover -s servidor-mcp/tests -v`
  - Resultado: `Ran 45 tests in 13.635s ... OK` (cobrindo `test_boundary.py`, `test_mcp_http.py`, `test_mrtr.py`, `test_precision_http.py` e `test_salas.py`).
  - Também foram verificadas as 20 checagens MCP de `validador/validar.py` (`verificar_mcp`): `PASS 01` a `PASS 20` (`20 PASS, 0 FAIL`).
  - Cobertura confirmada para catálogo/resource, consulta/reserva livre, os quatro erros de domínio da `001` mais `Sem alternativas disponiveis no intervalo`, alternativas/`accept`/`decline`/`cancel`, exigência de `_meta` e headers espelhados em chamadas iniciais e retries, e logs em `stderr` (`method`, `id`, `traceparent`) inclusive em rejeições de estado (`-32602`), header (`-32020`) e capability (`-32021`).
- **Reprodução em `.venv` nova, `curl` e restart a partir de outro `cwd` (`T028`)**:
  - Criada `.venv` limpa (`/tmp/venv-t028-mrtr`) com Python 3.12.12 e instalação editável (`-e ./servidor-mcp`), exportando `REQUEST_STATE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"` sem imprimir o segredo.
  - Processo 1 iniciado na raiz do repositório; enviado `request.body` extraído de `exemplos/wire/03-tools-call-conflito-input-required.json` via `curl`, obtendo `id: 3`, `resultType: "input_required"`, `enum: ["sala-fusca", "sala-mirante"]` e `requestState` (`<REDACTED_REQUEST_STATE>`).
  - Processo 1 encerrado e Processo 2 iniciado a partir de `/tmp` (`cd /tmp && ... python -m ponte_mcp`) mantendo o mesmo `REQUEST_STATE_SECRET`.
  - Enviado retry via `curl` com `id: 4` ecoando a chave capturada e o `requestState` opaco; resposta recebida com HTTP `200`, `resultType: "complete"`, `isError: false`, `structuredContent.reservado: true`, `sala: "sala-fusca"`, `inicio: "2026-11-03T14:00:00-03:00"`, `fim: "2026-11-03T15:00:00-03:00"`, `responsavel: "Marty"`, `politica: "2026-11-01"`.
  - `stderr` sanitizado confirmado:
    - Instância 1 (raiz): `[mcp] method=tools/call id=3 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
    - Instância 2 (`cwd=/tmp`): `[mcp] method=tools/call id=4 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **Auditoria de arquivos protegidos e escopo (`T029`)**:
  - `git status --short` e `git diff --stat dados/ exemplos/ validador/ README.md agente/` confirmam zero alterações em `dados/`, `exemplos/`, `validador/`, `README.md` e `agente/`.
  - Nenhuma dependência de LLM, banco de dados, ORM, autenticação, persistência em disco de reservas, store/sessão de continuação no servidor ou callback bidirecional foi introduzida.
  - Revisado `ConsumidorMCPDireto` em `servidor-mcp/tests/test_mrtr.py`: o consumidor guarda `requestState` em `NegociacaoCapturada.request_state` como string opaca e o ecoa literalmente em `build_retry_request_body` sem abrir, decodificar ou reconstruir o token.

## Consolidação de requisitos, princípios e passagem à ponte (T030)

### Cobertura de Requisitos Funcionais (`FR-001`–`FR-014`) e Critérios de Sucesso (`SC-001`–`SC-005`)

| Identificador | Evidência verificada | Status |
| --- | --- | --- |
| `FR-001` | `EstadoSalas.selecionar_alternativas` filtra salas livres no intervalo com `capacidade >= solicitada`, ordena por `(capacidade, id)` e limita a 3 (`TestAlternativasEConfirmacaoUS1T008`). | PASS |
| `FR-002` | `emitir_input_required` retorna `InputRequiredResult` (`resultType: "input_required"`, 1 entrada em `inputRequests` e `requestState` selado pelo SDK) sem criar reserva nem abrir callback (`TestUS1JornadaAcceptEAlternativasHTTP`). | PASS |
| `FR-003` | Entrada `elicitation/create` com `mode: "form"`, `requestedSchema` plano, propriedade `sala` string obrigatória e `enum` restrito às candidatas, inclusive com candidato único (`TestUS1JornadaAcceptEAlternativasHTTP`, `test_decline_cancel_sem_mutacao_e_candidato_unico_t022`). | PASS |
| `FR-004` | Quando todas as salas compatíveis estão ocupadas, retorna `complete` com `isError: true` e `Sem alternativas disponiveis no intervalo`, sem elicitation (`test_conflito_sem_alternativas_escolha_fora_do_schema_e_ocupacao_pos_oferta`). | PASS |
| `FR-005` | `verificar_capability_elicitation_form` exige `clientCapabilities.elicitation.form` no request atual e lança `MCPError(-32021)` com HTTP `400` e `data.requiredCapabilities: {"elicitation": {"form": {}}}` (`test_matriz_capabilities_por_request_conflito_reserva_livre_e_sem_alternativas_t021`). | PASS |
| `FR-006` | `PayloadRetomadaMRTR` selado via `RequestStateSecurity` (AES-256-GCM AEAD oficial do SDK `mcp==2.3.0`, `ttl=600`, `audience="ponte-salas"`). | PASS |
| `FR-007` | `ler_segredo_estado` lê exclusivamente `REQUEST_STATE_SECRET` (>= 32 bytes em hex), falha no startup se ausente/inválido/curto e nunca expõe o segredo (`TestStartupEConfiguracaoT032`). | PASS |
| `FR-008` | Zero memória de continuação no servidor; retry conclui após restart real do subprocesso MCP mantendo o mesmo `REQUEST_STATE_SECRET` e `SERVER_NAME` (`test_restart_real_preserva_retomada_rejeita_chave_trocada_e_mantem_expiracao_t017`, `T028`). | PASS |
| `FR-009` | Consumidor usa `id` JSON-RPC novo no retry e envia `inputResponses` + `requestState`; omissão isolada de um dos campos, mapa vazio, chave divergente ou entrada extra retorna `-32602` sem fallback para chamada inicial (`test_matriz_negativa_integridade_argumentos_incompletos_correlacao_e_payload_t016`). | PASS |
| `FR-010` | `RequestStateBoundary` verifica integridade AEAD e expiração (`ttl=600s`) antes do handler; adulteração ou expiração (inclusive após restart) gera `-32602` sem reserva (`TestUS2SegurancaIntegridadeExpiracaoERestartHTTP`). | PASS |
| `FR-011` | Digest SHA-256 canônico dos argumentos na `RequestStateBoundary` + conferência com `payload.original_arguments` rejeitam qualquer adulteração de `sala`, `inicio`, `fim` ou `responsavel` com `-32602` (`test_matriz_negativa_integridade_argumentos_incompletos_correlacao_e_payload_t016`). | PASS |
| `FR-012` | `accept` válido confirma reserva na alternativa escolhida preservando `inicio`, `fim`, `responsavel` e `politica` originais; revalida disponibilidade e retorna `complete`/`isError: true` se ocupada após a oferta (`TestUS1JornadaAcceptEAlternativasHTTP`). | PASS |
| `FR-013` | `decline` e `cancel` concluem com `resultType: "complete"`, `isError: false`, `structuredContent.reservado: false` e `motivo` (`"recusado"` / `"cancelado"`), sem mutar reservas (`test_decline_cancel_sem_mutacao_e_candidato_unico_t022`). | PASS |
| `FR-014` | Contrato puramente MCP com `requestState` opaco para o consumidor e sem conceitos de Task A2A no servidor MCP (`T029`). | PASS |
| `SC-001` | Conflito inicial em `sala-garagem` 14h–15h oferece exatamente `["sala-fusca", "sala-mirante"]` nessa ordem. | PASS |
| `SC-002` | `accept` conclui reserva preservando 100% dos dados originais exceto a sala escolhida. | PASS |
| `SC-003` | 100% das linhas negativas da matriz de aceite (token alterado/truncado, expirado, argumentos divergentes, continuação incompleta, correlação inválida, payload incompatível) recusadas com `-32602` e zero reservas criadas. | PASS |
| `SC-004` | Negociação emitida antes do restart conclui após reinício real do processo MCP dentro dos 600s originais. | PASS |
| `SC-005` | `decline` e `cancel` não criam nem removem reservas e concluem com `isError: false` e `reservado: false`. | PASS |

### Revisão dos Cinco Princípios Constitucionais

1. **Princípio I — Fidelidade ao Contrato dos Dois Protocolos**: preservado integralmente com o SDK oficial `mcp==2.3.0` (`InputRequiredResult`, `ElicitRequest`, `ElicitRequestFormParams`, `RequestStateSecurity`) sobre Streamable HTTP stateless em `/mcp`.
2. **Princípio II — Fronteira de Responsabilidade e Isolamento de Estado**: toda a seleção de alternativas, validação de política, proteção AEAD e confirmação de reserva vivem em `servidor-mcp/`; o consumidor trata `requestState` como token opaco.
3. **Princípio III — Estado Explícito por Requisição e Segurança do `requestState`**: `_meta` e headers validados a cada chamada (inicial e retry), `clientCapabilities.elicitation.form` verificado no request corrente sem herança, e `requestState` protegido por AES-256-GCM com `REQUEST_STATE_SECRET` (>= 32 bytes) e TTL de 600s.
4. **Princípio IV — Determinismo, Observabilidade e Arquivos Protegidos**: ordenação determinística `(capacidade, id)`, logs em `stderr` para todos os requests (incluindo rejeições `-32602`, `-32020`, `-32021`) e arquivos protegidos (`dados/`, `validador/`, `exemplos/`) intactos.
5. **Princípio V — Uso dos SDKs Oficiais, Escopo Enxuto e Entrega Reproduzível**: uso direto da `RequestStateBoundary` e `AESGCMRequestStateCodec` nativos do SDK `mcp==2.3.0`, sem reescrever o protocolo.

### Evidências de Comportamento do SDK `mcp==2.3.0` para o `README.md` Final (Spec 005)

- **Checagem granular de `elicitation.form`**: em `mcp==2.3.0`, `Connection.check_capability` (`mcp/server/connection.py`, linhas 253–254) verifica apenas `if capability.elicitation is not None and have.elicitation is None: return False`, não distinguindo `{"elicitation": {}}` ou `{"elicitation": {"url": {}}}` de `{"elicitation": {"form": {}}}` no caminho manual de `InputRequiredResult`. Por isso, `verificar_capability_elicitation_form` em `servidor-mcp/src/ponte_mcp/mrtr.py` inspeciona explicitamente `ctx.client_capabilities.elicitation.form is not None` e a chave `form` em `_meta["io.modelcontextprotocol/clientCapabilities"]["elicitation"]` antes de emitir `InputRequiredResult`, lançando `MCPError(code=MISSING_REQUIRED_CLIENT_CAPABILITY, ...)` com `MissingRequiredClientCapabilityErrorData` oficial do SDK.
- **União de retorno `ReservaOut | InputRequiredResult`**: em `mcp/server/mcpserver/utilities/func_metadata.py`, o SDK remove automaticamente `InputRequiredResult` da união ao gerar o `outputSchema` da tool (preservando o schema de `ReservaOut` em `tools/list`) e encaminha `InputRequiredResult` sem embrulhá-lo em `CallToolResult` quando retornado pelo handler, permitindo que `RequestStateBoundary` sele `result["requestState"]` com AES-256-GCM.

### Pendências para as Specs 003, 004 e 005

- **Spec 003**: implementação do cliente MCP no processo `agente/` (descoberta via `tools/list`, leitura de `politica://uso`, envio de `_meta` e headers espelhados, propagação de `traceparent`).
- **Spec 004**: implementação do servidor A2A v1.0 e da ponte de estado entre Tasks A2A (`TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_COMPLETED`, `TASK_STATE_CANCELED`, `TASK_STATE_FAILED`, isolamento de `requestState` opaco e `elicitation_key` por `taskId`).
- **Spec 005**: validação ponta a ponta com `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` com os dois processos recém-iniciados (exigindo 36/36 `PASS` e saída `0`), verificação a partir de clone limpo e consolidação do `README.md` final. O desafio completo **não** está declarado entregue nesta etapa.
