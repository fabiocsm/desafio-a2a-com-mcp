# A Ponte Constitution

## Core Principles

Os termos DEVE, DEVEM e NÃO DEVE expressam obrigações verificáveis. As permissões
explícitas preservam as alternativas aceitas pelo enunciado do desafio.

### I. Fronteiras reais e responsabilidade única

O projeto DEVE executar dois processos separados: servidor MCP em `servidor-mcp/`
e agente em `agente/`. O agente DEVE atuar como host/cliente MCP internamente e
servidor A2A externamente, acessando o MCP por HTTP. NÃO DEVE importar nem executar
diretamente funções das tools.

Somente o servidor MCP DEVE decidir política de uso, conflitos e alternativas.
O agente DEVE interpretar o formato fixo de entrada e traduzir os protocolos,
sem duplicar regras de domínio. O foco DEVE permanecer na ponte; ORM, banco de dados
e camadas de serviços desnecessárias ao domínio entregue NÃO DEVEM ser introduzidos.
Essa separação torna a integração real e verificável pelo avaliador.

### II. Estado explícito e ponte MRTR–A2A

Cada request DEVE transportar seus próprios metadados de protocolo. Nenhum lado
DEVE inferir versão, capabilities ou contexto de request anterior ou conexão aberta.
Reutilizar um objeto cliente MCP é permitido; reservas e Tasks em memória também
são permitidas, conforme as regras abaixo.

Em conflito com alternativas, o MCP DEVE encerrar a resposta com
`resultType: input_required`, uma única entrada em `inputRequests` e `requestState`.
A entrada DEVE ser `elicitation/create` em `mode: form`, com schema plano e a
propriedade obrigatória `sala` restrita às alternativas. Duas ou mais alternativas
DEVEM usar `enum`; para uma única alternativa, `enum` ou `const` são aceitos.
O servidor NÃO DEVE iniciar callback, aguardar resposta humana na chamada aberta
nem depender de estado de continuação guardado em memória.

O agente DEVE observar o `input_required` e colocar a Task em
`TASK_STATE_INPUT_REQUIRED`, devolvendo exatamente
`alternativas: <ids separados por virgula e espaco>`, na ordem do schema, sem
prefixos ou saudações. Um callback automático de elicitation NÃO DEVE consumir
a pergunta sem expor a pausa ao cliente A2A.

O estado de continuação DEVE ficar isolado por Task, incluindo pedido original,
alternativas, chave recebida em `inputRequests` e `requestState`. A retomada DEVE
repetir o `tools/call` original com id JSON-RPC diferente, levando `inputResponses`
e `requestState` dentro de `params`, com a mesma chave da pergunta. Duas Tasks
pausadas simultaneamente DEVEM concluir sem trocar seus estados.

Escolha fora do conjunto oferecido DEVE manter a pausa e repetir a mesma lista.
`escolha=recusar` DEVE virar `action: decline` e terminar a Task em
`TASK_STATE_CANCELED`. `decline` e `cancel` no MCP DEVEM produzir `complete`, sem
`isError: true`, com `structuredContent.reservado: false` e um `motivo`.

### III. Integridade e opacidade do requestState

O servidor DEVE tratar `requestState` como entrada controlada por atacante e proteger
sua integridade com HMAC ou AEAD. Cifrar é opcional; JSON em base64 sem assinatura
NÃO atende ao contrato. O estado DEVE expirar entre 5 e 30 minutos e carregar tudo
que permita reconstruir a operação sem memória de continuação no MCP.

A chave DEVE vir de `REQUEST_STATE_SECRET`, com pelo menos 32 bytes de aleatoriedade,
sem valor hardcoded nem segredo publicado. A documentação DEVE ensinar a gerar e
exportar a chave, por exemplo com
`python3 -c "import secrets; print(secrets.token_hex(32))"`, sem registrar seu valor.
Um estado ainda válido DEVE permitir retry após reinício do MCP com a mesma chave,
independentemente da perda das reservas criadas em memória.

Estado adulterado ou expirado DEVE gerar erro JSON-RPC `-32602`. Argumentos
reenviados que divirjam dos valores selados NÃO DEVEM alterar a operação: o servidor
DEVE rejeitar a divergência ou usar os valores selados.

Para o agente, `requestState` DEVE ser opaco: guardar e ecoar sem abrir, interpretar,
modificar ou reconstruir. NÃO DEVE aparecer no Agent Card, artifacts ou em qualquer
resposta A2A. A integridade desse estado NÃO DEVE ser confundida com autenticação.

### IV. Contratos exatos e execução determinística

O agente NÃO DEVE usar LLM no caminho de execução nem depender de SDK de provedor
de LLM nos manifestos. O mesmo pedido, sob o mesmo estado inicial, DEVE produzir
o mesmo resultado; reservas já criadas DEVEM afetar consultas posteriores.
Identificadores de Tasks e requests DEVEM respeitar os contratos de identidade.

Os formatos de entrada DEVEM ser exatamente
`reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>` e, na retomada
da mesma Task, `escolha=<id da sala>` ou `escolha=recusar`.
Mensagens, schemas, erros, estados e artifacts DEVEM obedecer aos contratos abaixo
e aos exemplos completos de `exemplos/wire/`. As variações de SDK expressamente
aceitas pelo desafio DEVEM continuar aceitas; não se DEVE forçar a imitação de outro SDK.

`dados/`, `validador/` e `exemplos/` NÃO DEVEM ser alterados, movidos ou reescritos.
Esses artefatos fornecem dados, política e contratos externos de avaliação.
As cinco salas e as reservas iniciais DEVEM ser carregadas dos JSON fornecidos.

### V. Conformidade demonstrável e rastreabilidade

A entrega DEVE passar nas 36 verificações do validador original, com os dois
processos recém-iniciados e código de saída 0. Passar no validador NÃO dispensa
os critérios de aceite e as verificações manuais exigidas pelo enunciado.

Cada request recebido pelo MCP DEVE ser registrado em stderr com método, id e
`traceparent` quando presente em `_meta`. O agente DEVE propagar para todos os
requests MCP de uma Task o mesmo trace-id recebido no header A2A `traceparent`;
o span-id pode mudar. Os logs DEVEM demonstrar descoberta antes da primeira chamada
de tool e ids diferentes para chamada inicial e retry.

Limitação real do SDK DEVE ser documentada no README com trecho de evidência.
NÃO DEVE ser contornada reescrevendo o protocolo nem usada para declarar cumprido
um critério ausente. A evidência permite avaliar a entrega sem ocultar lacunas.

## Restrições e contratos obrigatórios

- Stack: SDK oficial MCP v2 alinhado à revisão `2026-07-28`, usando
  `@modelcontextprotocol/server` em Node.js 20+ com ESM ou `mcp` em Python 3.10+.
  A2A DEVE ser v1.0 com binding JSON-RPC 2.0 sobre HTTP. Versões de dependências
  DEVEM ser travadas em `package.json` ou `pyproject.toml`. O validador exige Python 3.10+.
- Endpoints padrão: agente em `7300`, JSON-RPC em `/a2a` e card em
  `/.well-known/agent-card.json`; MCP em `7301`, endpoint único `/mcp`, via
  Streamable HTTP. Parametrização por ambiente é permitida com esses padrões.
- Metadados MCP: todo request DEVE incluir em `params._meta`
  `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities`.
  Ausência de qualquer um DEVE gerar `-32602` com HTTP `400`.
  O agente DEVE declarar `elicitation.form` em cada request, como em
  `{"elicitation": {"form": {}}}`. Esse objeto exemplifica a capability obrigatória,
  não uma lista exclusiva: capabilities adicionais anunciadas pelo SDK, como
  `elicitation.url`, são permitidas. A validação DEVE verificar a presença de
  `form` com valor objeto, sem exigir igualdade do objeto inteiro de capabilities.
  O fluxo de reserva continua usando `mode: form`, sem resposta automática.
  Quando uma chamada exigir elicitation sem essa capability, o servidor DEVE
  responder `-32021`, `data.requiredCapabilities` com o que faltou e HTTP `400`.
- Headers MCP: os requests do agente DEVEM espelhar o corpo em `MCP-Protocol-Version`,
  `Mcp-Method` e, para `tools/call` e `resources/read`, `Mcp-Name`.
  Divergência entre header e corpo DEVE ser recusada com `-32020`.
- Descoberta: o servidor DEVE declarar capabilities `tools` e `resources`.
  O agente DEVE executar `tools/list` antes da primeira chamada de tool, sem lista
  fixa de ferramentas no código, e ler `politica://uso`, extraindo a versão da primeira linha.
- Tools: DEVEM existir `listar_salas` sem parâmetros, `consultar_disponibilidade`
  com `sala`, `inicio`, `fim`, e `reservar_sala` com esses campos e `responsavel`.
  Todas DEVEM declarar `inputSchema` como objeto JSON Schema válido e devolver
  `structuredContent` e o mesmo JSON serializado em bloco de texto nos resultados completos.
  `listar_salas` DEVE declarar `outputSchema` compatível com o resultado.
  A consulta DEVE indicar disponibilidade e reservas em conflito, aplicando as
  mesmas validações de sala e política da reserva.
- Reserva concluída: o `structuredContent` DEVE conter `reserva`, `reservado`,
  `sala`, `inicio`, `fim`, `responsavel` e `politica`, conforme o contrato fornecido.
- Resource: `politica://uso` DEVE devolver o conteúdo de `dados/politica-de-uso.md`
  com `mimeType: text/markdown`. URI inexistente DEVE gerar `-32602`, nunca `contents` vazio.
- Política: reservas DEVEM respeitar 08:00–20:00 no horário de São Paulo (`-03:00`),
  duração máxima de duas horas, fim posterior ao início e ausência de sobreposição
  na mesma sala. Datas no passado DEVEM ser aceitas; nenhuma regra depende de hoje.
  Reservas criadas DEVEM ficar visíveis nas consultas seguintes do mesmo processo;
  persistência após reinício não é exigida.
- Alternativas: DEVEM ser salas livres no intervalo com capacidade maior ou igual
  à sala pedida, no máximo três, ordenadas por capacidade crescente e depois por
  `id` alfabético. Sem alternativas, a tool DEVE devolver o erro de execução previsto,
  sem elicitation.
- Erros de execução: DEVEM vir em resultado `complete` com `isError: true`.
  A mensagem exata da tabela abaixo DEVE aparecer no conteúdo; prefixo do SDK é aceito.
  Tool inexistente DEVE ser recusada por `-32602` ou por `isError: true`, conforme o SDK.

| Condição | Mensagem obrigatória |
| --- | --- |
| Sala inexistente | `Sala inexistente: <id informado>` |
| Início ou fim fora da janela | `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00` |
| Duração acima de duas horas | `Duracao acima do limite: a politica permite no maximo 2 horas` |
| Fim menor ou igual ao início | `Intervalo invalido: fim deve ser posterior a inicio` |
| Conflito sem alternativa | `Sem alternativas disponiveis no intervalo` |

- Agent Card: o GET DEVE responder HTTP `200` com card A2A v1.0 contendo identidade,
  capabilities, interface JSON-RPC com URL do endpoint e `protocolVersion: "1.0"`,
  e skill de id `reservar-sala`, conforme `exemplos/wire/07-a2a-agent-card.json`.
- Tasks: `/a2a` DEVE aceitar `SendMessage` e `GetTask`. Sem `taskId`, `SendMessage`
  DEVE criar Task com `id` e `contextId` próprios. A Task DEVE passar por
  `TASK_STATE_SUBMITTED` e `TASK_STATE_WORKING`; `GetTask` DEVE refletir a qualquer
  momento sua identidade, estado corrente e artifacts existentes.
- Resultados A2A: sucesso DEVE terminar em `TASK_STATE_COMPLETED`, com artifact de
  `name: reserva` contendo em parte de texto o JSON da reserva criada e `politica`
  com a versão lida do resource. Erro de execução da tool DEVE terminar em
  `TASK_STATE_FAILED`, preservando a mensagem exata no histórico.
  `TASK_STATE_COMPLETED`, `TASK_STATE_CANCELED` e `TASK_STATE_FAILED` DEVEM ser
  definitivos; `SendMessage` dirigido a Task terminal DEVE ser recusado com erro.
- Escopo: NÃO DEVEM ser introduzidos autenticação/autorização, OAuth, tokens,
  `securitySchemes` efetivos, streaming A2A, `SendStreamingMessage`, SSE, push,
  refinamento de Task, `referenceTaskIds`, continuidade entre Tasks, card estendido
  autenticado, JWS do card, prompts MCP, subscriptions ou progress.
  Container, compose, deploy, gateway, interface gráfica, persistência em disco das
  reservas, spans/atributos OpenTelemetry e mecanismos de transação ou concorrência
  de escrita para reservas no mesmo milissegundo também ficam fora do escopo.
  O transporte Streamable HTTP exigido permanece obrigatório.

## Fluxo de desenvolvimento e critérios de entrega

1. Antes de escrever código de aplicação, DEVEM ser lidos todos os exemplos de
   `exemplos/wire/`. Cada especificação, plano e conjunto de tarefas DEVE identificar
   os contratos e princípios afetados, com critérios de aceite verificáveis.
2. A implementação DEVE permitir verificar separadamente MCP, MRTR, host MCP,
   servidor A2A e ponte completa. A sequência sugerida é descoberta e schemas,
   validações e reserva simples, MRTR protegido, cliente MCP e, então, A2A e retomada.
   Essa sugestão não substitui nenhum requisito de entrega.
3. Antes da entrega, DEVEM ser reiniciados os dois processos e executado
   `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`.
   As 36 verificações DEVEM passar com saída 0, sem alterações no validador original.
4. A revisão DEVE também conferir logs de descoberta, trace-id e ids de retry;
   adulteração e expiração de estado; argumentos adulterados; retry após restart
   MCP com a mesma chave; rejeição por capability ausente; escolha inválida;
   cancelamento; erro de domínio; isolamento de duas Tasks pausadas; imutabilidade
   de estados terminais; e ausência de `requestState` nas respostas A2A.
5. O README da entrega DEVE substituir o enunciado por quatro seções: **Como rodar**,
   com comandos exatos para os dois processos e o validador a partir de clone limpo;
   **Onde a ponte acontece**, apontando o código da pausa e do retorno do estado;
   **Decisões técnicas**, explicando proteção, validade do `requestState` e armazenamento
   das Tasks; **Saída do validador**, com a saída completa da última execução em bloco
   de código. A geração/exportação do segredo DEVE estar documentada sem seu valor.
6. A entrega DEVE ser um único repositório público no GitHub, fork de
   `https://github.com/devfullcycle/desafio-a2a-com-mcp`, na branch `main`, mantendo
   `dados/`, `validador/`, `exemplos/`, `servidor-mcp/` e `agente/` em suas posições.
   Scripts auxiliares podem ficar na raiz. Os comandos do README DEVEM ser
   verificados em clone limpo antes do push final, e o link do fork DEVE ser entregue.

## Governance

Esta constituição governa especificações, planos, tarefas, implementação e revisão.
Ela consolida os requisitos do README original do desafio; substituir o README pela
documentação da solução NÃO revoga esses requisitos. Os artefatos protegidos e as
regras externas de avaliação NÃO podem ser relaxados por decisão local. Uma lacuna
ou divergência DEVE ser registrada e resolvida antes de declarar conformidade.

Toda alteração desta constituição DEVE registrar motivação, princípios afetados,
impacto nos artefatos e critérios de validação. Mudanças de governança DEVEM receber
aprovação explícita do mantenedor e avaliação de migração quando afetarem trabalho
existente. Uma nova edição DEVE atualizar a versão e a data de alteração,
preservando a data de ratificação original.

O versionamento DEVE seguir MAJOR.MINOR.PATCH: MAJOR para remoção ou redefinição
incompatível de princípios; MINOR para novos princípios, seções ou expansão material
de orientação; PATCH para esclarecimentos sem mudança semântica. A versão `1.0.0`
constitui a primeira adoção, em `2026-10-22`.

Cada revisão de especificação, plano, tarefas ou mudança de código DEVE verificar
os cinco princípios e os contratos aplicáveis, registrando evidências e pendências.
Falhas obrigatórias DEVEM bloquear a declaração de entrega concluída. Exceções já
aceitas pelo enunciado não exigem emenda; conveniências de implementação não criam
novas exceções. Templates e comandos DEVEM consultar esta constituição em runtime.
O Sync Impact Report é material temporário e DEVE ser removido antes do commit
da constituição, após a revisão da alteração.

## Histórico de esclarecimentos

- **1.0.1 — 2026-10-22**: Por instrução explícita do mantenedor, corrigida a
  interpretação que proibia anunciar `elicitation.url` junto de `elicitation.form`.
  O enunciado exige form, sem exclusividade de capabilities. Esclarecimento dos
  princípios II, IV e V, sem alteração das fronteiras do princípio I ou da
  integridade/opacidade do princípio III. Impacto: orientações, specs 003/005,
  tarefas e gates passam a verificar form em cada request e a aceitar capabilities
  adicionais. Validação: testes de wire e regressão MCP/A2A, incluindo rejeição de
  clientes sem form; dados, exemplos e validador original permanecem protegidos.

**Version**: 1.0.1 | **Ratified**: 2026-10-22 | **Last Amended**: 2026-10-22
