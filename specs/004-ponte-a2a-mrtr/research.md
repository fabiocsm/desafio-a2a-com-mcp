# Research: Ponte A2A–MRTR com pausa e retomada por Task

**Data**: 2026-10-22

Pesquisa local do README, constituição, spec e exemplos, complementada por fontes
primárias dos SDKs e metadados de versões publicadas. Agentes de pesquisa fizeram
inspeção somente leitura; não instalaram dependências no projeto.

## R01 — Continuação privada por Task

**Decision**: TaskRecord guarda Task pública separada de PendingContinuation; serialização retorna somente Task. Guardar o token como str opaca, parâmetros originais e pergunta recebida.

**Rationale**: O estado não pode vazar nem ser trocado entre Tasks. Um modelo público com metadata arbitrária é serializável e facilitaria o vazamento acidental.

**Alternatives considered**: Token em history/artifact/metadata, mapa global de última negociação ou interpretação do token pelo agente violam os requisitos.

## R02 — Retomada raw e ids

**Decision**: Criar uma nova session.call_tool com allow_input_required=True a cada continuação, passando input_responses/request_state e argumentos originais. O SDK atribui novo id, verificado em log.

**Rationale**: São requests independentes; a alternativa escolhida pertence ao content da resposta, não à substituição de params.arguments.sala. Preservar argumentos mantém o binding do estado.

**Alternatives considered**: Reenviar um envelope completo com id antigo ou usar Client.call_tool auto-fulfill destrói o contrato da pausa.

## R03 — Resultados e terminalidade

**Decision**: Tratar INPUT_REQUIRED como interrompido; só reentrar em WORKING após decisão válida. Decline percorre o MCP, complete confirma/cancela, isError e falha técnica terminam FAILED. Todos os terminais limpam a continuação.

**Rationale**: A Task deve representar o estado real da operação. O cliente não deve ver confirmação se a retomada falhou ou cancelamento local sem resposta MCP.

**Alternatives considered**: Considerar INPUT_REQUIRED terminal impede continuação; reabrir COMPLETED/CANCELED/FAILED pode duplicar reservas; limpar estado em escolha inválida perde a negociação.

## R04 — Testes além do validador

**Decision**: Adicionar teste de duas Tasks em ordem inversa, trace preservado sem header de continuação e busca de todos os tokens privados nas respostas.

**Rationale**: A verificação 34 procura somente prefixo de um estado conhecido; ela não prova ausência de qualquer token de qualquer Task. O teste de isolamento não precisa ampliar o escopo para corridas de escrita no mesmo intervalo.

**Alternatives considered**: Aprovar somente pelo validador deixa lacunas reais de privacidade e contexto. Adicionar banco, transações ou cenários de carga não é necessário.

## Evidências e fontes primárias

- [MRTR manual no cliente, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs_src/mrtr/tutorial002.py)
- [Sessão do cliente MCP, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/session.py)
- [Rotas JSON-RPC do A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_routes.py)
- [RequestHandler A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/request_handlers/request_handler.py)
- [Dispatcher e envelopes A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_dispatcher.py)
- [Migração de modelos A2A v1.0](https://github.com/a2aproject/a2a-python/blob/v1.2.3/docs/migrations/v1_0/README.md)

- [Pydantic 2.12.0 — publicação](https://pypi.org/project/pydantic/2.12.0/)
- [Starlette 0.48.0 — publicação](https://pypi.org/project/starlette/0.48.0/)
- [Uvicorn 0.31.1 — publicação](https://pypi.org/project/uvicorn/0.31.1/)
- [SSE-Starlette 3.0.3 — publicação](https://pypi.org/project/sse-starlette/3.0.3/)

## Resultado da pesquisa

Decisões de design resolvidas, sem esclarecimentos bloqueantes. Os pins foram
verificados em metadados publicados; a combinação MCP/A2A/Starlette/Uvicorn/SSE/Pydantic teve
resolução pip dry-run bem-sucedida direcionada a Python 3.12, sem instalação no
projeto. Isso demonstra resolução de dependências, não execução da aplicação nem
compatibilidade funcional já testada. A instalação e os testes pertencem à implementação.
