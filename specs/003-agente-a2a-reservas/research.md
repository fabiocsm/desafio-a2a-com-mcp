# Research: Agente A2A para descoberta e reservas diretas

**Data**: 2026-10-22

Pesquisa local do README, constituição, spec e exemplos, complementada por fontes
primárias dos SDKs e metadados de versões publicadas. Agentes de pesquisa fizeram
inspeção somente leitura; não instalaram dependências no projeto.

## R01 — SDK A2A e handler mínimo

**Decision**: Usar a2a-sdk[http-server]==1.2.3, rotas create_jsonrpc_routes/create_agent_card_routes e RequestHandler com on_message_send e on_get_task.

**Rationale**: A versão publicada suporta A2A 1.0 e usa tipos Protobuf; as assinaturas foram conferidas no wheel/tag, evitando APIs legadas. O handler simples mantém o controle explícito do fluxo determinístico.

**Alternatives considered**: DefaultRequestHandlerV2 com AgentExecutor e TaskStore é válido, mas inclui mecanismos de eventos desnecessários para este desafio. A2AFastAPIApplication/A2AStarletteApplication são referências antigas. JSON-RPC e serialização escritos à mão duplicariam o SDK.

## R02 — Perfil A2A do starter

**Decision**: No ServerCallContextBuilder público, estabelecer versão 1.0 apenas quando A2A-Version estiver ausente em /a2a. Manter o valor explícito intacto e o modo de compatibilidade 0.3 desativado.

**Rationale**: A norma interpreta ausência como 0.3, enquanto o starter envia SendMessage/GetTask v1 sem header. Sem adaptação do contexto o dispatcher oficial recusa os pedidos de avaliação. Os bodies, métodos e modelos permanecem inalterados.

**Alternatives considered**: Ativar fallback 0.3 não corrige métodos PascalCase v1. Alterar o validador é proibido. Reescrever o dispatcher ou mascarar versão explicitamente incompatível não é aceitável.

## R03 — Cliente MCP e elicitation

**Decision**: Usar Client(url, mode='2026-07-28', elicitation_callback=callback_defensivo) e chamadas client.session.call_tool com allow_input_required=True. tools/list e leitura de resource permanecem explícitos.

**Rationale**: O callback permite o anúncio exigido de form, mas o caminho raw evita que ele decida pelo cliente A2A. O SDK injeta envelope e headers. A versão fixa evita discovery/initialize automático sem trace contextualizável.

**Alternatives considered**: Client.call_tool fecha MRTR automaticamente. Requests HTTP artesanais eliminariam o benefício do SDK. A API desta versão anuncia também url; documentar essa limitação em vez de alterar atributos privados.

## R04 — Estado, parsing e rastreamento

**Decision**: Task pública somente com identidade, estado, histórico e artifact; parser por gramática fixa; contexto de trace explícito por Task/chamada; política extraída do resource.

**Rationale**: O cliente precisa de resultado e rastreabilidade, não de duplicação do domínio. O parse pode aceitar o texto final de responsavel com espaços sem usar linguagem natural.

**Alternatives considered**: Objeto global com último traceparent mistura Tasks. Recalcular regras no agente quebra a fronteira. A política hardcoded no artifact deixa de demonstrar consumo do resource.

## R05 — Dependências HTTP

**Decision**: Fixar a2a-sdk[http-server] 1.2.3, MCP 2.3.0, Starlette 0.48.0, Uvicorn 0.31.1 e sse-starlette 3.0.3, sem habilitar streaming.

**Rationale**: A resolução pip direcionada a Python 3.12 passou; fixar SSE evita deriva e backtracking para versões incompatíveis de Starlette. httpx de A2A e httpx2 do MCP são pacotes distintos e podem coexistir.

**Alternatives considered**: Instalar extras all traz SQL, gRPC e telemetry que não fazem parte da entrega. Resolver para versões latest sem pins não atende ao enunciado.

## Evidências e fontes primárias

- [MRTR manual no cliente, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs_src/mrtr/tutorial002.py)
- [Sessão do cliente MCP, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/session.py)
- [A2A SDK 1.2.3 — publicação](https://pypi.org/project/a2a-sdk/1.2.3/)
- [Rotas JSON-RPC do A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_routes.py)
- [RequestHandler A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/request_handlers/request_handler.py)
- [Dispatcher e envelopes A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_dispatcher.py)
- [Context builder público A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/common.py)
- [Versionamento normativo A2A v1.0](https://a2a-protocol.org/v1.0.0/specification/#36-versioning)
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
