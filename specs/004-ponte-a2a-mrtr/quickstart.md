# Quickstart: Ponte A2A–MRTR com pausa e retomada por Task

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

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
Use ponte_task_id em GetTask; o estado deve continuar pausado. Não use o id
ilustrativo dos exemplos 09/10.

## Continuar sem reenviar traceparent

```bash
python -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":"continuar-1","method":"SendMessage","params":{"message":{"messageId":"continua-msg-1","role":"ROLE_USER","taskId":sys.argv[1],"parts":[{"text":"escolha=sala-fusca"}]}}}))' "$ponte_task_id" |
curl -sS http://127.0.0.1:7300/a2a   -H 'Content-Type: application/json' --data-binary @-
```

Esperado: mesma Task COMPLETED e artifact de sala-fusca, horário/responsável originais.
No stderr MCP, conferir novo id JSON-RPC e o trace-id do pedido inicial.
Nenhuma resposta pode conter token privado.

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
