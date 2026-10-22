# Quickstart: Reserva com alternativas e retomada MRTR segura

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

## Preparação e startup

Concluir 001 e implementar 002. Ativar a .venv e atualizar o pacote:

```bash
. .venv/bin/activate
python -m pip install -e ./servidor-mcp
export REQUEST_STATE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp
```

Conserve a mesma variável no terminal ao interromper e reiniciar o processo.
Não gere outra chave entre a pergunta e o retry.

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
