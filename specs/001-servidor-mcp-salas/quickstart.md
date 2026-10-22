# Quickstart: Servidor MCP de salas e reservas diretas

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

## Pré-requisitos e instalação prevista

Python 3.12+ e os arquivos originais. Os manifests e o pacote abaixo serão criados
na implementação da 001; execute depois dela:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./servidor-mcp
export REQUEST_STATE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp
```

Mantenha o terminal aberto. A variável pertence ao servidor; não publicar seu valor.
O processo deve servir http://127.0.0.1:7301/mcp. No segundo terminal, ative a mesma
.venv. O módulo encaminha o lifespan do app SDK ao Uvicorn e usa um worker.

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
