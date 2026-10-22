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
subprocessos e limpa o estado. Os testes da aplicação ainda não foram executados.

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
