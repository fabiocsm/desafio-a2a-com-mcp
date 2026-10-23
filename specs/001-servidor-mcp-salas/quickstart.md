# Quickstart: Servidor MCP de salas e reservas diretas

Guia de validação executada para a feature `001-servidor-mcp-salas`. Execute comandos
a partir da raiz do repositório, salvo indicação contrária.

## Pré-requisitos e instalação

Python 3.12+ e os arquivos originais do starter. Para gerar a chave de integridade
sem publicá-la no repositório:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Ambiente virtual novo, instalação editável e inicialização do servidor MCP:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./servidor-mcp
export REQUEST_STATE_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp
```

Mantenha o terminal aberto. A variável `REQUEST_STATE_SECRET` pertence ao servidor e
nunca deve ter seu valor registrado em arquivos versionados. O processo atende em
`http://127.0.0.1:7301/mcp` (parametrizável via `MCP_HOST` e `MCP_PORT`), encaminha o
lifespan do app SDK ao Uvicorn e utiliza um único worker.

## Descoberta real sem enviar o wrapper do exemplo

```bash
python -c 'import json; print(json.dumps(json.load(open("exemplos/wire/01-tools-list.json"))["request"]["body"]))' |
curl -sS http://127.0.0.1:7301/mcp   -H 'Content-Type: application/json'   -H 'Accept: application/json, text/event-stream'   -H 'MCP-Protocol-Version: 2026-07-28'   -H 'Mcp-Method: tools/list'   --data-binary @-
```

Esperado: as três tools e schemas de objeto. O arquivo de exemplo é documentação:
envie somente request.body. Não envie o JSON externo inteiro.

## Verificações da feature

```bash
python -m unittest discover -s servidor-mcp/tests -p 'test_salas.py' -v
python -m unittest discover -s servidor-mcp/tests -p 'test_mcp_http.py' -v
```

Os testes devem cobrir cinco salas, política integral, reserva livre/consulta seguinte,
quatro erros exatos em ambas as tools, limites 08h/20h/2h, passado, adjacência,
metadata faltante com/sem header, divergência de headers e logging de rejeições.
Para reserva livre, use o request.body do exemplo 02 e Mcp-Name: reservar_sala,
reiniciando antes para que o horário esteja livre. Confira a consulta seguinte.

A lista detalhada está em [contrato](contracts/mcp.md) e [modelo](data-model.md).
A validação oficial integral exige o agente e a ponte das features seguintes;
não declarar 36 PASS com esta feature isolada.

## Evidências executadas — US2 (T017)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_salas.py' -v` (`Ran 8 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mcp_http.py' -v` (`Ran 4 tests ... OK`)
- **Resultados verificados**:
  - Descoberta em `tools/list` dos handlers reais `consultar_disponibilidade` e `reservar_sala` com `inputSchema` de objeto e `required` correspondentes às assinaturas.
  - Jornada `consultar_disponibilidade` (livre) → `reservar_sala` (argumentos do exemplo 02) → `consultar_disponibilidade` (ocupada com a reserva recém-criada) e consulta da reserva inicial de Marty (`res-0001`) sem mutação.
  - Equivalência entre `structuredContent` e `content[].text` tanto em `consultar_disponibilidade` quanto em `reservar_sala`.
  - Restart real do subprocesso MCP comprovando recarga das reservas originais de `dados/reservas.json` sem exigir persistência da reserva transitória e mantendo `dados/`, `exemplos/` e `validador/` inalterados.
  - **Fronteira de escopo (FR-015)**: a reserva sob conflito (MRTR com `input_required`, `elicitation/create` e `requestState`) pertence ao incremento `002-reserva-mrtr-segura` e não possui evidência funcional nesta spec.

## Evidências executadas — US1 + US2 (T023)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_salas.py' -v` (`Ran 10 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mcp_http.py' -v` (`Ran 5 tests ... OK`)
- **Resultados verificados**:
  - Gate integral de descoberta das três tools reais (`listar_salas`, `consultar_disponibilidade` e `reservar_sala`) com `inputSchema` de objeto e `outputSchema` declarado em `listar_salas`.
  - `listar_salas` devolve as cinco salas idênticas a `dados/salas.json` com equivalência exata entre `structuredContent` e o JSON em `content[].text`.
  - `resources/read` de `politica://uso` devolve `text/markdown` e o texto integral sem perda de bytes, com versão da primeira linha (`2026-11-01`) coincidente com o campo `politica` da reserva criada na US2.
  - Tool inexistente (`voar_delorean`) recusada com `isError: true` e URI de resource inexistente (`politica://inexistente`) recusada com `-32602` (HTTP 400), sem `contents` vazio.
  - Registros em `stderr` conferidos com `method`, `id` e `traceparent` das chamadas de descoberta e leitura de resource.

## Evidências executadas — US3 (T031)

- **Comandos executados**:
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_salas.py' -v` (`Ran 12 tests ... OK`)
  - `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_mcp_http.py' -v` (`Ran 8 tests ... OK`)
- **Resultados verificados**:
  - Matriz dos quatro erros exatos de domínio (`Sala inexistente: <id>`, `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`, `Duracao acima do limite: a politica permite no maximo 2 horas` e `Intervalo invalido: fim deve ser posterior a inicio`) validada tanto em `consultar_disponibilidade` quanto em `reservar_sala` (em unidade e via HTTP real), sempre com `resultType: complete` e `isError: true`, sem criar reservas.
  - Precedência determinística (`sala` → `intervalo` → `janela` → `duração`) e rejeição de formatos inválidos/sem timezone sem inventar mensagem de domínio.
  - Matriz de metadados ausentes em `params._meta` (`protocolVersion` ausente, `clientCapabilities` ausente, ambos ausentes, `_meta` ausente, com e sem header moderno `MCP-Protocol-Version`, após requests válidos com capabilities diversas): 100% recusados com `-32602` e HTTP `400`, sem herança de sessão ou contexto.
  - Matriz de divergências isoladas de headers (`MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` em `tools/call` e `resources/read`): recusadas pelo transporte oficial do SDK com `-32020` e HTTP `400`.
  - Evidência de comportamento do SDK `mcp==2.3.0`: em `mcp/server/streamable_http_manager.py` (`_handle_request`, `TODO(L49)`), chamadas sem o header `MCP-Protocol-Version` são roteadas ao caminho legado; por isso a guarda ASGI em `ponte_mcp/entrada.py` valida estritamente a presença de `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities` em `params._meta` antes de delegar ao SDK.
  - Registros em `stderr` verificados para chamadas válidas e rejeitadas (metadata, headers, tool inexistente, URI inexistente), com e sem `traceparent`, sem expor `REQUEST_STATE_SECRET`.

## Reprodução limpa, preservação de artefatos e revisão final (T032–T035)

### Revisão da fronteira HTTP — R1-2, R1-3 e R1-4

- `.venv/bin/python -m unittest discover -s servidor-mcp/tests -p 'test_boundary.py' -v`: 6 testes passam após reproduzir falhas na implementação anterior. A matriz HTTP recusa headers ausentes/legados ou divergentes antes de reservar; metadados ausentes mantêm `-32602` e envelopes malformados seguem para rejeição pelo SDK.
- `classify_inbound_request` público do SDK agora valida os headers após `JSONRPCRequest`; `RequestBodyLimitMiddleware` externo recusa `Content-Length` excedente sem ler e interrompe chunks ao cruzar 4 MiB, antes do parse. `subscriptions=False` mantém tools/resources, desliga subscribe/listChanged e recusa `subscriptions/listen` com `-32601`/HTTP 404 sem stream aberto.
- `PYTHONPATH=servidor-mcp/tests .venv/bin/python -m unittest test_mcp_http.TestUS3RejeicoesDominioProtocoloELogsHTTP -v`: 3 testes passam, preservando logs, metadados e erros de domínio existentes. As evidências anteriores acima descrevem a execução histórica anterior à revisão.

### Startup, configuração e ambiente virtual novo (T032, T033)

- `test_startup_a_partir_de_outro_cwd_e_override_host_porta` e `test_valores_padrao_e_rejeicao_segredo_invalido_sem_vazamento` (`TestStartupEConfiguracaoT032`):
  - Inicialização verificada a partir de `cwd` temporário externo ao repositório, resolvendo `dados/` pelo pacote instalado em modo editável.
  - Valores padrão `MCP_HOST=127.0.0.1` e `MCP_PORT=7301` e overrides testados.
  - `REQUEST_STATE_SECRET` ausente, hexadecimal inválido ou com menos de 32 bytes decodificados falha no startup com código de saída diferente de zero e sem vazar o segredo em `stdout`/`stderr`.
- Ambiente `.venv` recriado do zero com `python3.12 -m venv .venv`, `python -m pip install -e ./servidor-mcp`, subida real de `python -m ponte_mcp`, descoberta via `curl` enviando exclusivamente `request.body` de `exemplos/wire/01-tools-list.json` (registrando `[mcp] method=tools/list id=1 traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` em `stderr`), e suítes completas passando (`12` testes em `test_salas.py` e `10` testes em `test_mcp_http.py`).

### Preservação dos artefatos protegidos e escopo (T034)

- `git diff --stat -- dados/ exemplos/ validador/ README.md agente/` vazio; `git status --short` contém apenas arquivos autorizados em `servidor-mcp/` e `specs/001-servidor-mcp-salas/`.
- Nenhuma dependência de SDK de LLM, ORM, banco de dados, autenticação, SSE de produto, containers ou persistência em disco foi introduzida em `servidor-mcp/pyproject.toml`.

### Revisão dos cinco princípios constitucionais e matriz de requisitos (T035)

| Princípio | Status na 001 | Evidência |
| --- | --- | --- |
| I. Fronteiras reais e responsabilidade única | PASS | Processo isolado em `servidor-mcp/src/ponte_mcp/`; zero imports de `agente/`; domínio somente em memória sobre `dados/`. |
| II. Estado explícito e ponte MRTR–A2A | PASS (base MCP) | Transporte `stateless_http=True`, `json_response=True`, exigência estrita de `params._meta` por request sem herança de sessão. |
| III. Integridade e opacidade do `requestState` | PASS (preparação) | `RequestStateSecurity` configurado com `REQUEST_STATE_SECRET` (>= 32 bytes) e `audience="ponte-salas"`, TTL de 600s, pronto para `002`. |
| IV. Contratos exatos e execução determinística | PASS | Schemas, `structuredContent`, `content[].text`, política integral e quatro mensagens exatas de erro verificados; arquivos protegidos intactos. |
| V. Conformidade demonstrável e rastreabilidade | PASS (escopo 001) | Logs em `stderr` com `method`, `id` e `traceparent` em chamadas válidas e rejeitadas; evidência de roteamento do SDK documentada para inclusão na seção **Decisões técnicas** do README final na `005`. |

| Requisito / Critério | Status | Evidência executada |
| --- | --- | --- |
| FR-001 | PASS | Subprocesso real em `/mcp`, porta padrão `7301` e overrides testados (`test_mcp_http.py`). |
| FR-002 | PASS | `tools/list` e `resources/list` anunciam `listar_salas`, `consultar_disponibilidade`, `reservar_sala` e `politica://uso`. |
| FR-003 | PASS | Todas as tools possuem `inputSchema` de objeto; `listar_salas` declara `outputSchema` compatível. |
| FR-004 | PASS | Equivalência `structuredContent` e `content[].text` validada nas três tools (`TestUS1DescobertaSalasEPoliticaHTTP`, `TestUS2ConsultaEReservaLivreHTTP`). |
| FR-005 | PASS | Reservas iniciais carregadas, reserva livre visível na consulta seguinte e recarga limpa após restart (`test_restart_real_recarrega_reservas_originais_e_preserva_arquivos`). |
| FR-006 | PASS | Validação compartilhada com timezone obrigatório, conversão para `-03:00`, janela `08:00`–`20:00` no mesmo dia, limite de 2h e datas no passado (`test_salas.py`). |
| FR-007 | PASS | `consultar_disponibilidade` informa `sala`, `livre` e `conflitos` sem mutar reservas (`test_consulta_sala_livre_e_ocupada_sem_mutacao`). |
| FR-008 | PASS | `reservar_sala` em horário livre retorna `resultType: complete`, `isError: false` e todos os campos obrigatórios (`test_jornada_consultar_reservar_consultar_e_descoberta_us2`). |
| FR-009 | PASS | Quatro mensagens exatas e precedência `sala` → `intervalo` → `janela` → `duração` verificadas nas duas operações (`TestMatrizRejeicoesUS3`, `test_quatro_erros_dominio_em_consultar_e_reservar_via_http`). |
| FR-010 | PASS | `politica://uso` retorna `text/markdown` integral; URI inexistente retorna `-32602` e HTTP `400`. |
| FR-011 | PASS | Tool inexistente recusada com `isError: true`. |
| FR-012 | PASS | Ausência de `protocolVersion` ou `clientCapabilities` em `params._meta` retorna `-32602` e HTTP `400` com ou sem header moderno (`test_matriz_metadados_ausentes_e_headers_divergentes`). |
| FR-013 | PASS | Divergências de `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` retornam `-32020` e HTTP `400`. |
| FR-014 | PASS | `stderr` registra `method`, `id` e `traceparent` em chamadas aceitas e rejeitadas (`test_logs_stderr_para_sucessos_e_rejeicoes_com_e_sem_traceparent`). |
| FR-015 | PENDENTE (002) | Fronteira preservada sem contrato provisório; o ciclo MRTR em `reservar_sala` sob conflito será implementado na feature `002-reserva-mrtr-segura`. |
| SC-001 a SC-004 | PASS | Todos os quatro critérios mensuráveis da spec 001 comprovados pelas suítes `test_salas.py` (12 testes) e `test_mcp_http.py` (10 testes). |

- **Pendências para as próximas features**:
  - `002-reserva-mrtr-segura`: alternativas ordenadas, `input_required` com `elicitation/create` em `mode: form`, `-32021` sem capability, retry com `inputResponses` e `requestState` AEAD, recusa (`decline`/`cancel`), erro `Sem alternativas disponiveis no intervalo` e retomada após restart MCP.
  - `003-agente-a2a-reservas`: host/cliente MCP e servidor A2A v1.0 (`/.well-known/agent-card.json`, `SendMessage`, `GetTask`, propagação de `traceparent`, reserva direta e falha de domínio).
  - `004-ponte-a2a-mrtr`: pausa `TASK_STATE_INPUT_REQUIRED`, guarda opaca de `requestState` por Task, continuação com id JSON-RPC novo, cancelamento e imutabilidade de estados terminais.
  - `005-conformidade-entrega`: gate integral das 36 verificações de `validador/validar.py` com os dois processos recém-iniciados, verificações manuais e substituição final do `README.md`.
