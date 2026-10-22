# Contract: Conformidade, reprodução e documentação da entrega

## Instalação e configuração pública

Os manifests serão servidor-mcp/pyproject.toml e agente/pyproject.toml.
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
- --agente URL_BASE e --mcp URL_MCP, com os padrões do projeto.
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
