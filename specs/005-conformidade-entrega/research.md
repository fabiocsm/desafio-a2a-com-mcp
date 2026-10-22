# Research: Conformidade, reprodução e documentação da entrega

**Data**: 2026-10-22

Pesquisa local do README, constituição, spec e exemplos, complementada por fontes
primárias dos SDKs e metadados de versões publicadas. Agentes de pesquisa fizeram
inspeção somente leitura; não instalaram dependências no projeto.

## R01 — Reprodução e dependências

**Decision**: Dois pacotes Python instalados em venv limpa; pins diretos nos manifests e constraints.txt com resolução completa, sem entradas editáveis locais.

**Rationale**: O avaliador segue apenas o README de um clone limpo. O pacote A2A e o MCP compartilham dependências HTTP e precisam da combinação já pesquisada, incluindo sse-starlette 3.0.3.

**Alternatives considered**: Instalação global, versões latest, caminhos absolutos congelados ou arquivos de ambiente com segredos prejudicam a reprodução. Container/compose e deploy estão fora de escopo.

## R02 — Evidência automática real

**Decision**: Executar o validador original integralmente com processos recém-iniciados e salvar a saída completa e o status de execução sem mascará-lo.

**Rationale**: O validador tem 36 verificações e altera a disponibilidade; ele não permite selecionar testes por feature. A documentação deve conter a última execução real da versão entregue.

**Alternatives considered**: Execução repetida sem restart produz falsos negativos. Recortar somente linhas PASS, inventar saída ou adaptar o validador é inválido.

## R03 — Evidência adicional

**Decision**: Usar o script para restart manual, trace-id/ids e fluxos públicos/privacidade; usar a suíte HTTP/subprocesso da feature 002 para integridade, expiração com relógio controlado no servidor isolado, argumentos e capability, mantendo TTL 600 de produção. Complementar a varredura HTTP com os testes de serialização e tokens sentinela da 004. Registrar resultados sem valores secretos/token e identificar o método de cada prova, sem apresentar mocks do suporte como execução dos protocolos.

**Rationale**: O README do validador explicita que logs e restart não são demonstrados pela suíte. Há ainda limites na verificação de vazamento que justificam teste complementar.

**Alternatives considered**: Aprovar apenas com 36 PASS é insuficiente. Spans OpenTelemetry, carga, banco e infraestrutura não acrescentam evidência exigida.

## R04 — Documentação de diferenças dos SDKs

**Decision**: Documentar AEAD oficial, raw MCP, perfil A2A sem header e GetTask como Task direta no SDK, citando fonte e efeito observável. Registrar o anúncio form+url como pendência de conformidade de 003/FR-008, não como variação aceita; manter a aceitação da 005 bloqueada até solução por API pública compatível e teste do wire exato aprovado. Se a correção exigir mudança de pin, consolidar somente versões exatas efetivamente validadas nas duas aplicações e nas constraints.

**Rationale**: O enunciado aceita apenas as variações explicitadas, como GetTask direto, e exige evidência de limitações reais sem reescrever protocolo. Essa documentação não dispensa capabilities exatas nem permite aprovar um requisito ausente. O perfil A2A também deve ser descrito sem prometer negociação normativa irrestrita.

**Alternatives considered**: Esconder adaptação, imitar snapshots de outra stack ou modificar SDK/validador tornaria a entrega difícil de avaliar.

## Evidências e fontes primárias

- [MCP 2.3.0 — publicação e requisitos](https://pypi.org/project/mcp/2.3.0/)
- [Segurança RequestStateSecurity, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/request_state.py)
- [Sessão do cliente MCP, tag v2.3.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/session.py)
- [A2A SDK 1.2.3 — publicação](https://pypi.org/project/a2a-sdk/1.2.3/)
- [Rotas JSON-RPC do A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_routes.py)
- [Dispatcher e envelopes A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/jsonrpc_dispatcher.py)
- [Context builder público A2A SDK 1.2.3](https://github.com/a2aproject/a2a-python/blob/v1.2.3/src/a2a/server/routes/common.py)
- [Versionamento normativo A2A v1.0](https://a2a-protocol.org/v1.0.0/specification/#36-versioning)
- [Migração de modelos A2A v1.0](https://github.com/a2aproject/a2a-python/blob/v1.2.3/docs/migrations/v1_0/README.md)

- [Pydantic 2.12.0 — publicação](https://pypi.org/project/pydantic/2.12.0/)
- [Starlette 0.48.0 — publicação](https://pypi.org/project/starlette/0.48.0/)
- [Uvicorn 0.31.1 — publicação](https://pypi.org/project/uvicorn/0.31.1/)
- [SSE-Starlette 3.0.3 — publicação](https://pypi.org/project/sse-starlette/3.0.3/)

## Resultado da pesquisa

Design de entrega decomposto, com dependência de conformidade ainda pendente em
003/FR-008 e sem solicitação de dispensa ao usuário. Os pins de base foram
verificados em metadados publicados; a combinação MCP/A2A/Starlette/Uvicorn/SSE/Pydantic teve
resolução pip dry-run bem-sucedida direcionada a Python 3.12, sem instalação no
projeto. Isso demonstra resolução de dependências, não execução da aplicação nem
compatibilidade funcional já testada. A instalação e os testes pertencem à implementação.
