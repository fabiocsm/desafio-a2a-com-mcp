# Quickstart: Ponte A2A–MRTR com pausa e retomada por Task

Guia de validação da ponte. Execute comandos a partir da raiz do repositório,
salvo indicação contrária. A feature 005 consolida o README, o clone limpo e a
entrega do fork; esses gates não são declarados cumpridos aqui.

## Gate da base (T001)

Antes da ponte, a base 001–003 já respondia. Conferência nesta etapa, com os
pacotes editáveis do `.venv` e sem alterar `dados/`, `validador/` ou `exemplos/`:

- `python -m unittest discover -s servidor-mcp/tests -v` — 45 testes, OK.
- `python -m unittest discover -s agente/tests -v`, ainda sem `test_ponte.py` — 22 testes, OK.
- Descoberta, `politica://uso`, reserva livre, MRTR manual e callback defensivo
  já existiam em `ponte_mcp` e `ponte_agente`. Nenhuma pendência bloqueou o avanço.

## Preparação

Implementar 001–004 e seguir a instalação da [003](../003-agente-a2a-reservas/quickstart.md).
Iniciar MCP e agente em terminais separados, com a mesma chave MCP preservada para
testes de restart. Começar com os dois processos recém-iniciados.

## Exercitar a pausa e capturar a identidade real

No terceiro terminal, na raiz do repositório:

```bash
ponte_pause_file="$(mktemp)"
python -c 'import json; print(json.dumps(json.load(open("exemplos/wire/08-a2a-send-message.json"))["request"]["body"]))' |
curl -sS http://127.0.0.1:7300/a2a   -H 'Content-Type: application/json'   -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'   --data-binary @- > "$ponte_pause_file"
cat "$ponte_pause_file"
ponte_task_id="$(python -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["result"]["task"]["id"])' "$ponte_pause_file")"
```

Esperado: INPUT_REQUIRED e linha exata alternativas: sala-fusca, sala-mirante.
Não use o id ilustrativo dos exemplos 09/10. Consulte a identidade capturada:

```bash
python -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":"consultar-pausa-1","method":"GetTask","params":{"id":sys.argv[1]}}))' "$ponte_task_id" |
curl -sS http://127.0.0.1:7300/a2a -H 'Content-Type: application/json' --data-binary @-
```

Esperado: mesmos id/contextId, estado INPUT_REQUIRED e pergunta original.
O SDK pode devolver a Task diretamente em `result`; o wrapper `result.task` do
exemplo também é aceito pelo validador. Não alterar a serialização do SDK.

## Continuar sem reenviar traceparent

```bash
python -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":"continuar-1","method":"SendMessage","params":{"message":{"messageId":"continua-msg-1","role":"ROLE_USER","taskId":sys.argv[1],"parts":[{"text":"escolha=sala-fusca"}]}}}))' "$ponte_task_id" |
curl -sS http://127.0.0.1:7300/a2a   -H 'Content-Type: application/json' --data-binary @-
```

Esperado: mesma Task COMPLETED e artifact de sala-fusca, horário/responsável originais.
No stderr MCP, conferir novo id JSON-RPC e o trace-id do pedido inicial.
Nenhuma resposta pode conter token privado.

Consultar novamente a mesma Task:

```bash
python -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":"consultar-conclusao-1","method":"GetTask","params":{"id":sys.argv[1]}}))' "$ponte_task_id" |
curl -sS http://127.0.0.1:7300/a2a -H 'Content-Type: application/json' --data-binary @-
rm "$ponte_pause_file"
```

Esperado: mesma identidade, COMPLETED e artifact `reserva` com sala-fusca,
horário/responsável originais e versão da política lida do resource.

## Testes da ponte

```bash
python -m unittest discover -s agente/tests -p 'test_ponte.py' -v
```

A suíte deve reiniciar os serviços para cenários que exigem base limpa e cobrir:
escolha inválida seguida de válida; recusa real; GetTask pausado; const; erros
de tool e protocolo; todos os terminais; duas Tasks retomadas em ordem inversa;
mesmas pausas para pedidos iguais; trace sem novo header; nenhum token em respostas.
Não ampliar o teste para disputa simultânea de escrita no mesmo milissegundo.

Após esta etapa, a solução funcional está apta à execução oficial integral;
a feature 005 organiza a reprodução e as evidências finais.

## Onde a pausa e o retry acontecem

A Task pública e a continuação privada ficam separadas em `agente/src/ponte_agente/tasks.py`.
`pause_for_input` (por volta da linha 380) grava `PendingContinuation` e só então
publica `TASK_STATE_INPUT_REQUIRED`. `repeat_pause` (linha 405) devolve o mesmo
`pause_text` sem chamar o MCP. `begin_resume` (linha 429) volta a `WORKING` e
mantém o token. `_clear_private_continuation` (linha 363) zera `pending` em
`COMPLETED`, `CANCELED` e `FAILED`. `GetTask` continua devolvendo só a cópia da Task.

A tradução do formulário está em `continuation_from_input_required`
(`agente/src/ponte_agente/ponte.py`, linha 47): uma elicitation `form`, ordem de
`enum` ou `const` único, chave recebida e `requestState` literal.

O handler pausa em `_pause_from_input_required` (`handler.py`, linha 218) e
retoma em `_resume_task` (linha 244). O retry chama `call_tool_raw` (linha 263)
com os argumentos originais, a chave original, o token ecoado e o trace da Task.
Escolha inválida ou Task terminal retornam antes dessa chamada. O id JSON-RPC
novo é fornecido por `UniqueRequestDispatcher` via `CallOptions.request_id`, API
pública do SDK; o agente não reenvia o envelope anterior nem altera contadores
internos. Cada operação abre e fecha transporte e sessão oficiais na mesma
coroutine, sem deixar uma falha de rede inutilizar o host de Tasks futuras.
Antes de chamar a tool, a sessão descobre todas as páginas com o trace da Task,
preservando também a validação de outputSchema pelo SDK. Se a conexão cair, a
Task termina em `FAILED`, limpa sua continuação e não repete a operação: a reserva
pode ter sido efetivada antes da perda da resposta. Erro JSON-RPC, inclusive
estado expirado, também não é repetido nem renovado.

## Evidências desta etapa

Execução real, processos HTTP recém-iniciados, sem publicar segredo nem token:

```bash
python -m unittest discover -s agente/tests -v
```

38 testes, OK. Inclui os casos diretos de 003 e `agente/tests/test_ponte.py`.
`dados/` permaneceu byte a byte igual ao início da suíte.

Casos com os dois processos reais: pausa de sala-garagem 14:00–15:00, GetTask,
`escolha=sala-fusca`, artifact `reserva` com política `2026-11-01` lida do
resource; escolha `sala-aquario` repetindo a mesma linha e só então a escolha
válida; `escolha=recusar` com `action: decline` e salas alternativas ainda
livres; Tasks `COMPLETED`, `CANCELED` e `FAILED` recusando outra mensagem sem
novo `tools/call`; conflito sem alternativa com a mensagem exata; duas Tasks
retomadas em ordem inversa com traces distintos; dois pedidos iguais com a
mesma pausa; Task sem `traceparent` que não herda o trace da outra; restart só
do MCP, com a mesma chave, e retomada da Task que continuou no agente.

Casos controlados, sem o domínio real: enum fora de ordem alfabética, `const`
de uma sala, chave variável, token sentinela, `isError` com `reservado: false`
virando `FAILED`, erro `-32602` e falha de conexão. Nesses, o texto público não
contém o sentinela.

O teste HTTP de pausa observou, no proxy, `tools/list` antes do primeiro
`tools/call`, argumentos originais no retry, `content.sala` só na resposta
`accept`, cabeçalhos `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name`,
capability `elicitation.form` e ids JSON-RPC diferentes entre a chamada inicial
e o retry. O stderr do MCP registrou método, id e o trace-id da Task.

### Validador oficial

Processos novos em `127.0.0.1:7301` (`/mcp`) e `127.0.0.1:7300` (`/a2a`),
`REQUEST_STATE_SECRET` só no ambiente do MCP. Saída de
`python3 validador/validar.py --agente http://127.0.0.1:7300 --mcp http://127.0.0.1:7301`:

```text
trace-id desta execucao: 2d624cadbf032f3f98dda00c3eb25195
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

No stderr do MCP, o trace-id `2d624cadbf032f3f98dda00c3eb25195` apareceu na
descoberta e nas chamadas do agente, com span-id diferente a cada request:

```text
[mcp] method=tools/list id=1 traceparent=00-2d624cadbf032f3f98dda00c3eb25195-b4c84be4085f2e8f-01
[mcp] method=resources/read id=2 traceparent=00-2d624cadbf032f3f98dda00c3eb25195-f478f6534f7571a0-01
[mcp] method=tools/call id=3 traceparent=00-2d624cadbf032f3f98dda00c3eb25195-62795e07ac7e3f96-01
[mcp] method=tools/call id=4 traceparent=00-2d624cadbf032f3f98dda00c3eb25195-bb705150208954db-01
[mcp] method=tools/call id=5 traceparent=00-2d624cadbf032f3f98dda00c3eb25195-84a6bd59cd40c1cb-01
```

Os ids 3, 4 e 5 são chamadas distintas. As verificações 15, 17 e 18 cobrem, no
MCP real, capability ausente, estado adulterado e argumentos adulterados. A
expiração com relógio controlado permanece na suíte de 002
(`servidor-mcp/tests/test_mrtr.py`), que passou junto com os outros 44 testes
desse processo. O agente não abre o token para tratar `-32602`: a Task vai a
`FAILED` com `Falha ao executar pedido no servidor MCP`.

### Limitação observada do SDK

O servidor registra falha de tool com prefixo do SDK. No mesmo stderr:

```text
Tool 'reservar_sala' failed: 'Error executing tool reservar_sala: Sem alternativas disponiveis no intervalo'
Tool 'reservar_sala' failed: 'Error executing tool reservar_sala: Sala inexistente: sala-delorean'
```

A Task `FAILED` preserva a mensagem de domínio no fim do texto. O enunciado
aceita esse prefixo. Não houve contorno de protocolo.

O id JSON-RPC usa UUID via a opção pública do dispatcher oficial. A prova de id
novo é o log e o corpo capturado, sem ler contador interno do SDK. A regressão de
queda HTTP perde a resposta depois de um efeito observado, exige um único envio,
confere `FAILED`, limpa os dados privados, consulta `GetTask` e conclui uma nova
Task após restauração. Outra Task pausada antes da falha retoma com id diferente
e seu trace original. O teste de restart também conecta agente e MCP diretamente,
sem proxy, e verifica no stderr ids distintos e o mesmo trace-id. O callback de
elicitation existe para anunciar `form`; com `allow_input_required=True` o SDK
devolve `InputRequiredResult` e o callback não roda. Reiniciar o agente perde
as Tasks em memória; o restart exigido é o do MCP, com a Task ainda no agente.
