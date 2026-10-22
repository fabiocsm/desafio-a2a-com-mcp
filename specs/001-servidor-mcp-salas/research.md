# Research: Servidor MCP de salas e reservas diretas

**Data**: 2026-10-22

Pesquisa local do README, constituição, spec e exemplos, complementada por fontes
primárias dos SDKs e metadados de versões publicadas. Agentes de pesquisa fizeram
inspeção somente leitura; não instalaram dependências no projeto.

## R01 — Stack e execução

**Decision**: Python 3.12+, SDK mcp==2.3.0 e app ASGI oficial servido por Uvicorn. Usar os pins do Technical Context.

**Rationale**: A publicação 2.3.0 oferece MCPServer v2 e revisão moderna, além das primitivas de MRTR necessárias à próxima feature. Uma stack única reduz diferenças entre os processos.

**Alternatives considered**: TypeScript server/client 2.3.1 foi confirmado como alternativa válida; não foi escolhido para evitar duas toolchains. MCP v1, framework MCP de terceiros e transporte artesanal foram descartados.

## R02 — Dados e política

**Decision**: Ler os JSON e o texto originais; usar modelos Pydantic de saída, datetimes com timezone e interseção de intervalos semiabertos. Gerar identificadores de reserva por contador sem colisão com os dados carregados.

**Rationale**: O domínio é pequeno e o starter é a fonte dos dados. O contador precisa garantir unicidade no processo, sem prometer persistência.

**Alternatives considered**: Banco, ORM, camada de repositório e dependência da data corrente violariam ou ampliariam o desafio. Strings de data comparadas sem parsing não garantem a política.

## R03 — Transporte moderno, metadados e logging

**Decision**: Configurar Streamable HTTP stateless e resposta JSON; observar entrada ASGI e exigir os dois metadados, com rejeição tipada oficial. Após validar o envelope com JSONRPCRequest, delegar coerência dos headers e protocolo ao classificador público classify_inbound_request do SDK, antes do roteamento legado. Usar RequestBodyLimitMiddleware com o limite padrão externamente à guarda e subscriptions=False no MCPServer.

**Rationale**: O middleware interno do MCP fica depois de fronteiras que podem rejeitar requests; sozinho não registra tudo. A fonte streamable_http_manager.py mostra roteamento legado quando falta o header, então o perfil precisa rejeitar metadados ausentes e headers contraditórios também nessa entrada. O limitador deve executar antes da observação que lê o corpo; a opção pública de subscriptions evita o stream e as capabilities ativados por padrão pelo SDK.

**Alternatives considered**: Logging apenas nas tools perde falhas de protocolo. Inferir metadata do header viola o enunciado. Reimplementar o dispatcher ou importar APIs privadas do transporte não será permitido.

## R04 — Erros e resultados

**Decision**: Manter as cinco mensagens do enunciado como constantes de contrato, com erro sem alternativas reservado à 002. Resultados completos usam structuredContent e texto com JSON equivalente.

**Rationale**: O avaliador compara mensagens e estrutura; prefixos de erro do SDK são aceitos. Models e schemas devem refletir o contrato real.

**Alternatives considered**: Alterar mensagens para acentuação ou texto amigável diferente, devolver contents vazio para URI inválida ou ocultar erros em sucesso são incompatíveis.

## Evidências e fontes primárias

- [MCP 2.3.0 — publicação e requisitos](https://pypi.org/project/mcp/2.3.0/)
- [MCPServer e app ASGI, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/mcpserver/server.py)
- [Segurança RequestStateSecurity, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/request_state.py)
- [Roteamento por era do transporte MCP](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/streamable_http_manager.py)

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
