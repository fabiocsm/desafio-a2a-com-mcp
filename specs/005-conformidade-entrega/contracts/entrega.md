# Contract: Conformidade, reprodução e documentação da entrega

## Instalação e configuração pública

Os manifests serão servidor-mcp/pyproject.toml e agente/pyproject.toml.
Pré-condição de aceitação: 003/FR-008 aprovado com capabilities exatamente
`{"elicitation": {"form": {}}}` em cada request MCP do agente. Anúncio form+url
mantém o gate reprovado; documentá-lo não constitui cumprimento do contrato.
Uma eventual revisão de pin deve ser exata e testada na feature de origem antes
de consolidar manifests e constraints da entrega.

Pacotes instaláveis em modo editável oferecem:
- python -m ponte_mcp — loopback 7301, /mcp.
- python -m ponte_agente — loopback 7300, /a2a e card well-known.

Configuração padrão:
- MCP_HOST=127.0.0.1, MCP_PORT=7301, somente no servidor.
- AGENTE_HOST=127.0.0.1, AGENTE_PORT=7300.
- MCP_URL=http://127.0.0.1:7301/mcp no agente.
- A2A_BASE_URL=http://127.0.0.1:7300 para a interface publicada no card.
- REQUEST_STATE_SECRET obrigatório no MCP, hex de pelo menos 32 bytes aleatórios.
- TTL 600s e nome/audience ponte-salas estáveis.

## Protocolo do verificador adicional planejado

scripts/verificar_entrega.py usa biblioteca padrão e argumentos:
- --agente URL_BASE, padrão http://localhost:7300 (sem /a2a).
- --mcp URL_MCP, padrão http://localhost:7301/mcp (endpoint completo).
- --caso reinicio-mcp --fase emitir --estado CAMINHO_TEMP.
- --caso reinicio-mcp --fase retomar --estado CAMINHO_TEMP.
- --caso rastreamento --log-mcp CAMINHO_LOG.
- --caso privacidade para exercitar múltiplas Tasks e varrer respostas públicas.

A fase emitir guarda o token sem imprimi-lo. Entre fases, o operador reinicia
somente o MCP com a mesma chave. A fase retomar usa pedido/chave/token originais
com id novo; retorna sucesso só após confirmação real. O script não termina,
reinicia ou altera processos do usuário de maneira implícita.
Todas as verificações terminam com 0 em sucesso e valor não zero em falha.
O validador oficial continua inalterado e é executado separadamente.

Cada caso começa com processos recém-iniciados e base própria; não reutiliza a
base consumida pela suíte oficial nem por outro caso. No restart, somente o MCP
reinicia entre as fases, com a mesma chave/audience. O rastreamento inicia um fluxo
A2A próprio com trace-id exclusivo e agente limpo, exigindo descoberta anterior à
primeira chamada do agente, leitura da política e ids distintos na chamada/retry.
Um tools/list do cliente direto do validador não comprova descoberta do agente.

Integridade/expiração/argumentos/capability são exercitados pela suíte HTTP da 002,
não por uma opção implícita deste script. Estado adulterado/expirado gera -32602;
conflito que exige form sem essa capability gera -32021/HTTP 400/requiredCapabilities.
Para argumentos divergentes, rejeição ou uso dos valores selados são aceitos,
sempre sem efeito dos valores adulterados. A expiração pode usar relógio controlado
apenas no servidor isolado do teste, sem reduzir TTL ou simular o transporte.

## Aceitação da entrega

| Evidência | Exigência |
| --- | --- |
| Suíte original | 36 PASS, zero FAIL, código 0 em base limpa |
| Arquivos protegidos | comparação com a base original sem diferenças |
| Trace/log | descoberta anterior à primeira tool, mesmo trace-id e id diferente no retry |
| Estado | integridade/expiração/argumentos e retomada após restart demonstrados |
| A2A | pausa/escolha/recusa/falha/terminais/isolamento/privacidade |
| README | quatro seções, comandos de clone limpo e saída completa real |
| Repositório | único fork público, estrutura mantida e entrega final na main |

A ausência de token/segredo nas respostas não dispensa não publicá-los em arquivos.
A presença de dependências transitivas SSE/OpenTelemetry não habilita streaming
ou instrumentação. Limitações reais são descritas com evidência e não tornam
um critério obrigatório automaticamente atendido.
