# Quickstart: Agente A2A para descoberta e reservas diretas

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

## Instalação e dois terminais

Após implementar 001/002 e 003, em ambiente Python 3.12+:

```bash
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

## Testes previstos

```bash
python -m unittest discover -s agente/tests -p 'test_agente_direto.py' -v
```

Cobrir GetTask, terminalidade, erro sala-delorean, origem da política, descoberta
anterior ao tools/call, metadados/headers e rastreamento. O stderr MCP deve conter
4bf92f3577b34da6a3ce929d0e0e4736, sem exigir span-id igual.

As chamadas diretas alteram reservas. Reinicie ambos antes de outra bateria.
Os testes de pausa não são critério de conclusão desta etapa isolada; seguir
para 004 e só então exigir a validação oficial integral.
