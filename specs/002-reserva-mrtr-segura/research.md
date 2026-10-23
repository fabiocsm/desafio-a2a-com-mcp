# Research: Reserva com alternativas e retomada MRTR segura

**Data**: 2026-10-22

Pesquisa local do README, constituição, spec e exemplos, complementada por fontes
primárias dos SDKs e metadados de versões publicadas. Agentes de pesquisa fizeram
inspeção somente leitura; não instalaram dependências no projeto.

## R01 — Proteção oficial do estado

**Decision**: Usar RequestStateSecurity(keys=[bytes.fromhex(REQUEST_STATE_SECRET)], ttl=600). O codec padrão é AES-256-GCM com derivação HKDF-SHA256, configurado uma vez com nome/audience estável.

**Rationale**: A tag v2.3.0 inclui confidencialidade e integridade, expiração e binding do pedido. A escolha atende a opção AEAD do enunciado e permite restart com a mesma configuração.

**Alternatives considered**: HMAC próprio seria permitido pelo enunciado, mas duplicaria utilitário pronto. Base64 simples, chave hardcoded e default RequestStateSecurity.ephemeral() não atendem à retomada após restart.

## R02 — MRTR manual

**Decision**: Retornar InputRequiredResult com input_requests e payload em request_state; no retry usar ctx.input_responses e ctx.request_state já verificado.

**Rationale**: O servidor encerra a resposta pedindo informação; não existe canal de volta no transporte. O payload deve conter todos os elementos necessários mesmo após perder a memória do processo.

**Alternatives considered**: Elicitation síncrona, callback do servidor ou dicionário de handles para negociações invalidariam o modelo stateless exigido.

## R03 — Checagem de capability

**Decision**: Antes da pergunta manual, exigir elicitation.form e usar MCPError(-32021) com requiredCapabilities. Deixar o transporte SDK mapear o erro para HTTP 400.

**Rationale**: A checagem automática do helper Resolve/Elicit não garante o caminho manual, e o fallback legado de elicitation genérica não satisfaz o form explícito do README.

**Alternatives considered**: Confiar apenas no suporte genérico de elicitation ou enviar a pergunta antes da checagem produziria comportamento inválido.

## R04 — Vinculação e expiração

**Decision**: Adotar a rejeição nativa de argumentos divergentes do envelope selado. Conferir expiração por relógio controlado nos testes e fazer restart real com estado ainda válido.

**Rationale**: A fronteira oficial sela método, alvo, digest de argumentos e claims temporais antes de retornar ao cliente; o id JSON-RPC não deve ser usado como vínculo porque precisa mudar.

**Alternatives considered**: Usar apenas os argumentos reenviados permite adulteração. Alterar TTL de produção para acelerar testes ou dormir dez minutos a cada teste não é necessário.

## Evidências e fontes primárias

- [MCP 2.3.0 — publicação e requisitos](https://pypi.org/project/mcp/2.3.0/)
- [MCPServer e app ASGI, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/mcpserver/server.py)
- [Segurança RequestStateSecurity, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/request_state.py)
- [Sessão do cliente MCP, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/session.py)
- [MRTR no SDK Python](https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/)
- [Resolve/Elicit e checagem de capability](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/mcpserver/resolve.py)

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
