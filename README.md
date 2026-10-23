# A Ponte

Reserva de salas com um servidor MCP e um agente A2A em processos separados.
A ponte traduz a pausa MRTR do MCP para uma Task A2A e devolve o `requestState` sem abri-lo.

## Como rodar

Pré-requisitos: Python 3.12 ou superior para os dois serviços e Python 3.10 ou superior para o validador. Os comandos abaixo usam Python 3.12.

A partir de um clone limpo, na raiz do repositório:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -c constraints.txt -e ./servidor-mcp -e ./agente
python -m pip check
```

Gere uma chave hexadecimal com pelo menos 32 bytes aleatórios e exporte-a no terminal do MCP. O valor não entra no repositório:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
export REQUEST_STATE_SECRET="<cole-aqui-a-saida>"
```

No primeiro terminal, com a chave exportada e o stderr visível:

```bash
. .venv/bin/activate
python -m ponte_mcp
```

No segundo terminal:

```bash
. .venv/bin/activate
python -m ponte_agente
```

Cada processo usa um worker. Os padrões são `MCP_HOST=127.0.0.1`, `MCP_PORT=7301`, `AGENTE_HOST=127.0.0.1`, `AGENTE_PORT=7300`, `MCP_URL=http://127.0.0.1:7301/mcp` e `A2A_BASE_URL=http://127.0.0.1:7300`. Os endpoints publicados são `http://127.0.0.1:7301/mcp`, `http://127.0.0.1:7300/a2a` e `http://127.0.0.1:7300/.well-known/agent-card.json`.

Com os dois processos recém-iniciados, no terceiro terminal:

```bash
. .venv/bin/activate
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

O comando termina com código 0 quando as 36 verificações passam. Reinicie os dois processos antes de cada nova rodada oficial, para restaurar as reservas iniciais. Para o teste de retomada, reinicie somente o MCP com a mesma `REQUEST_STATE_SECRET` e o mesmo nome `ponte-salas`.

Para continuar pelo fluxo manual do avaliador, **reinicie o MCP depois do
validador e antes do passo 7**, usando novamente `python -m ponte_mcp` no primeiro
terminal, com a mesma chave exportada. O validador cria reservas: ao terminar,
fusca e mirante já estão ocupadas em 03/11/2026 das 14h às 15h. Sem esse reinício,
o pedido da garagem retorna `Sem alternativas disponiveis no intervalo`, em vez
da pausa esperada. O agente pode continuar ativo; as Tasks existentes permanecem
consultáveis. Não reinicie o MCP entre a pausa e a escolha, exceto no teste
específico de retomada após restart.

Nos exemplos de `exemplos/wire/`, envie somente `request.body` como corpo do POST,
com os headers de `request.headers`. O arquivo inteiro inclui descrição e resposta
esperada, que não fazem parte do request. Em uma base recém-iniciada, o pedido do
exemplo 08 deve listar `alternativas: sala-fusca, sala-mirante`. Use o `taskId`
real recebido ao continuar com `escolha=sala-mirante` e ao consultar `GetTask`.
Depois do aceite, um novo pedido pode oferecer menos alternativas, pois a reserva
confirmada continua ocupando a sala. Uma nova Task ainda pode recusar com
`escolha=recusar` enquanto houver alternativa.

Verificações adicionais disponíveis, cada caso com MCP e agente recém-iniciados:

```bash
python scripts/verificar_entrega.py --caso privacidade
```

Esse caso verifica reserva direta, pausa, escolha inválida, duas Tasks retomadas
em ordem inversa, recusa, erro de domínio, consulta dos artifacts, rejeição nos três
estados terminais e ausência de estado privado nas respostas A2A. Para conferir
descoberta, propagação de trace-id e ids distintos no retry, suba uma base nova e
capture o stderr MCP no primeiro terminal:

```bash
python -m ponte_mcp 2> >(tee /tmp/ponte-mcp.stderr.log >&2)
```

No terceiro terminal, com o agente também recém-iniciado:

```bash
python scripts/verificar_entrega.py --caso rastreamento --log-mcp /tmp/ponte-mcp.stderr.log
```

Para provar a retomada após restart, comece com outra base nova e execute no
terceiro terminal:

```bash
ponte_state_file=$(mktemp /tmp/ponte-estado-XXXXXXXX)
trap 'rm -f "$ponte_state_file"' EXIT
python scripts/verificar_entrega.py --caso reinicio-mcp --fase emitir --estado "$ponte_state_file"
```

Reinicie **somente o MCP** no primeiro terminal, preservando a chave e mantendo o
agente ativo. Em menos de 600 segundos, no mesmo terceiro terminal:

```bash
python scripts/verificar_entrega.py --caso reinicio-mcp --fase retomar --estado "$ponte_state_file"
rm -f "$ponte_state_file"
```

O arquivo temporário guarda o token opaco fora do repositório. As suítes abaixo
complementam os testes HTTP com adulteração e expiração do estado, argumentos
divergentes, capability ausente e headers incompatíveis. Elas iniciam seus próprios
processos em portas temporárias:

```bash
python -m unittest discover -s servidor-mcp/tests -v
python -m unittest discover -s agente/tests -v
python -m unittest discover -s tests -v
```

## Onde a ponte acontece

O agente recebe o `InputRequiredResult` cru e só então publica a pausa.

- `continuation_from_input_required` e `pause_text_for` em `agente/src/ponte_agente/ponte.py` leem a única elicitation em `mode: form`, preservam a ordem do schema e montam `alternativas: <ids>`. O `requestState` fica no objeto privado, sem ser aberto.
- `AgenteRequestHandler._pause_from_input_required` em `agente/src/ponte_agente/handler.py` chama essa tradução e `TaskStore.pause_for_input`.
- A continuação entra em `AgenteRequestHandler._resume_task`. `build_retry_input_responses` monta `inputResponses` na chave original. `MCPHost.call_tool_raw` em `agente/src/ponte_agente/mcp_host.py` repete o `tools/call` com os argumentos originais, a mesma chave e o `requestState` ecoado. `UniqueRequestDispatcher.send_raw_request` atribui um id JSON-RPC novo (`ponte-<uuid>`).
- `TaskStore` e `PendingContinuation` em `agente/src/ponte_agente/tasks.py` isolam pedido, alternativas, chave e estado opaco por Task. A resposta pública sai de `clone_public_task`, que não inclui o token.

## Decisões técnicas

Os serviços exigem Python >=3.12. As dependências diretas estão pinadas em `servidor-mcp/pyproject.toml` e `agente/pyproject.toml`: `mcp==2.3.0`, `a2a-sdk[http-server]==1.2.3` (somente no agente), `starlette==0.48.0`, `uvicorn==0.31.1`, `sse-starlette==3.0.3` e `pydantic==2.12.0`. O backend de build é `hatchling==1.27.0`. `constraints.txt` é o `pip freeze --exclude-editable` de uma venv que contém só esses dois pacotes e a resolução deles.

O estado de continuação usa o codec oficial do SDK MCP 2.3.0, `AESGCMRequestStateCodec` (AES-256-GCM, chave derivada com HKDF-SHA256, prefixo `v1.`). `criar_mcp_server` em `servidor-mcp/src/ponte_mcp/app.py` configura `RequestStateSecurity` com TTL de 600 segundos e audience `ponte-salas`. `ler_segredo_estado` exige `REQUEST_STATE_SECRET` em hexadecimal, com pelo menos 32 bytes. O payload necessário para reconstruir a operação vai dentro do token; o processo MCP não guarda continuação em memória. Um retry com o mesmo token, id JSON-RPC novo e a mesma chave conclui a reserva depois de reiniciar só o MCP, desde que ocorra antes de 600 segundos.

Tasks e reservas criadas durante a execução ficam na memória do processo. Encerrar o agente descarta as Tasks. Encerrar o MCP recarrega `dados/reservas.json` e descarta reservas criadas naquela execução. Uma reserva criada permanece visível para as consultas seguintes do mesmo processo.

Diferenças observadas nos SDKs, sem alteração de protocolo:

- O `ClientSession` do MCP 2.3.0 anuncia `elicitation.form` e `elicitation.url` quando há callback de elicitation (`mcp/client/session.py`, tag v2.3.0). Cada request do agente leva `form` como objeto. A capability `url` adicional é permitida. O teste `test_gate_fr008_declara_form_em_cada_request_com_capabilities_adicionais` confere o `form` em cada request.
- `MCPHost.call_tool_raw` pede o resultado com `allow_input_required=True`. O `input_required` chega cru e o callback defensivo não responde no lugar da Task. O teste `test_callback_defensivo_nunca_executado_e_input_required_cru` cobre esse caminho.
- O roteador JSON-RPC do A2A SDK 1.2.3 aceita a chamada sem o header `A2A-Version`. `StarterProfileContextBuilder` em `agente/src/ponte_agente/app.py` aplica a versão `1.0` quando o header está ausente e preserva o valor quando o cliente o envia. A fonte normativa de versionamento é a especificação A2A v1.0, seção 3.6. Esta adaptação não é a negociação normativa irrestrita.
- `GetTask` no dispatcher do A2A SDK 1.2.3 (`_handle_get_task` em `a2a/server/routes/jsonrpc_dispatcher.py`) coloca a Task direta em `result`. `SendMessage` continua envolvendo a Task. O teste de `GetTask` aceita os dois formatos.

`sse-starlette` e `opentelemetry-api` aparecem na resolução porque os SDKs dependem deles. O servidor MCP usa Streamable HTTP com `json_response=True`. O card declara streaming e push desligados. Não há SDK de provedor de LLM nos manifestos.

## Saída do validador

Última execução oficial em 23/10/2026, com os dois processos recém-iniciados em
clone limpo de `8823afe`, venv nova e instalação pelos comandos acima. Código de
saída 0. Trace-id `895c54080dba05c0872abf9caddff073`. Esta revisão altera somente a
documentação; os serviços, manifests e constraints são os da revisão testada.
A [auditoria de conformidade](docs/evidencias/auditoria-2026-10-23.md) registra o
fluxo manual, os testes complementares e a pendência de publicação na `main`.

```text
trace-id desta execucao: 895c54080dba05c0872abf9caddff073
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```
