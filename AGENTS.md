# Orientações para agentes — A Ponte

## Antes de implementar

- Leia o `README.md`, a constituição em `.specify/memory/constitution.md` e todos
  os exemplos de `exemplos/wire/`. Os exemplos completos definem os contratos de wire.
- Respeite os requisitos e critérios de aceite do desafio. Este arquivo resume
  as orientações; não substitui os contratos detalhados da constituição e do enunciado.
- O foco é a ponte de estado entre MCP e A2A. Mantenha o domínio simples, sem ORM,
  banco de dados ou camadas de serviços desnecessárias.

## Arquitetura e arquivos protegidos

- Mantenha dois processos separados: servidor em `servidor-mcp/` e agente em `agente/`.
  O agente é host MCP por dentro e servidor A2A por fora; a comunicação entre os
  processos deve ocorrer por HTTP, sem importar funções das tools diretamente.
- Regras de sala, política, conflitos e alternativas pertencem ao servidor MCP.
  O agente apenas interpreta o formato fixo e traduz protocolos.
- Não altere, mova ou reescreva `dados/`, `validador/` ou `exemplos/`.
  Carregue salas e reservas iniciais dos JSON fornecidos e preserve a estrutura do starter.
- Não use LLM no caminho de execução nem adicione SDK de provedor de LLM aos manifestos.
  A execução deve ser determinística para o mesmo pedido e estado inicial.
- Não infira versão, capabilities ou contexto a partir de request anterior ou conexão.
  Reutilizar o objeto cliente MCP é permitido. Reservas e Tasks podem ficar em memória;
  reservas criadas devem afetar consultas seguintes do mesmo processo.

## Stack e endpoints

- Use SDK oficial MCP v2 alinhado à revisão `2026-07-28`:
  `@modelcontextprotocol/server` com Node.js 20+ e ESM ou `mcp` com Python 3.10+.
- Use A2A v1.0 com binding JSON-RPC 2.0 sobre HTTP.
- Trave versões de dependências no `package.json` ou `pyproject.toml`.
- Preserve os padrões abaixo, mesmo que permita configuração por ambiente.

| Processo | Porta | Endpoint |
| --- | --- | --- |
| Servidor MCP, Streamable HTTP | `7301` | `/mcp` |
| Agente A2A, JSON-RPC | `7300` | `/a2a` |
| Agent Card A2A v1.0 | `7300` | `/.well-known/agent-card.json` |

## Contrato MCP

- Declare capabilities `tools` e `resources`. Exponha `listar_salas` sem parâmetros,
  `consultar_disponibilidade(sala, inicio, fim)` e
  `reservar_sala(sala, inicio, fim, responsavel)` com `inputSchema` válido.
- Devolva `structuredContent` e o mesmo JSON serializado em bloco de texto.
  `listar_salas` deve declarar `outputSchema`. A reserva concluída deve incluir
  `reserva`, `reservado`, `sala`, `inicio`, `fim`, `responsavel` e `politica`.
- Exponha `politica://uso` com o conteúdo de `dados/politica-de-uso.md` e
  `mimeType: text/markdown`. URI inexistente gera `-32602`, nunca `contents` vazio.
- O agente deve descobrir tools com `tools/list` antes da primeira chamada,
  sem lista fixa no código, e ler a versão da política na primeira linha do resource.
- Inclua em `_meta` de cada request `io.modelcontextprotocol/protocolVersion` e
  `io.modelcontextprotocol/clientCapabilities`; ausência gera `-32602` com HTTP `400`.
  O agente declara `elicitation.form` em todos os requests MCP, como em
  `{"elicitation": {"form": {}}}`. Capabilities adicionais anunciadas pelo SDK,
  como `elicitation.url`, são permitidas; não exigir igualdade do objeto inteiro.
- Espelhe o corpo nos headers `MCP-Protocol-Version`, `Mcp-Method` e, em
  `tools/call` e `resources/read`, `Mcp-Name`. Divergência gera `-32020`.
- Registre cada request recebido pelo MCP em stderr com método, id e `traceparent`
  quando presente em `_meta`. Propague o mesmo trace-id recebido no header A2A
  para todos os requests MCP da Task; o span-id pode mudar.

## MRTR e segurança do estado

- Em conflito com alternativas, encerre a resposta com `resultType: input_required`,
  um `requestState` e uma única entrada em `inputRequests`: `elicitation/create`
  em `mode: form`, schema plano e propriedade obrigatória `sala` restrita às alternativas.
  Use `enum`; com uma única opção, `const` também é aceito.
- Não implemente callback do servidor nem mantenha a chamada aberta esperando o usuário.
  No agente, não deixe callback automático responder sem pausar a Task A2A.
- Se a chamada exigir elicitation e o cliente não declarar form mode, retorne
  `-32021` com HTTP `400` e `data.requiredCapabilities` indicando o que faltou.
- Proteja `requestState` com HMAC ou AEAD e expiração entre 5 e 30 minutos.
  Cifrar é opcional; base64 sem assinatura não basta. Estado adulterado ou expirado
  deve gerar `-32602`.
- Use `REQUEST_STATE_SECRET` com pelo menos 32 bytes de aleatoriedade, sem segredo
  hardcoded ou publicado. Documente geração e exportação, nunca o valor utilizado:

  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```

- O estado deve conter tudo para reconstruir a operação no MCP, sem memória de
  continuação no servidor, e funcionar após restart com a mesma chave e antes de expirar.
- No retry, leia `inputResponses` e `requestState` de `params`. Argumentos adulterados
  não podem produzir efeito: rejeite a divergência ou use os valores selados.
- No agente, guarde e ecoe `requestState` sem abrir, interpretar, alterar ou reconstruir.
  Nunca o exponha no card, artifact ou em qualquer resposta A2A.

## Tasks A2A e a ponte

- O card deve declarar identidade, capabilities, interface JSON-RPC com URL e versão
  `1.0`, e skill `reservar-sala`, conforme `exemplos/wire/07-a2a-agent-card.json`.
- Aceite `SendMessage` e `GetTask`. Sem `taskId`, crie Task com `id` e `contextId`
  próprios, passando por `TASK_STATE_SUBMITTED` e `TASK_STATE_WORKING`.
- Use o pedido fixo `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>`.
  A continuação usa o mesmo `taskId` com `escolha=<id da sala>` ou `escolha=recusar`.
- Ao receber `input_required`, coloque a Task em `TASK_STATE_INPUT_REQUIRED` e devolva
  exatamente `alternativas: <ids separados por virgula e espaco>`, na ordem do schema.
  Isole o pedido, alternativas, chave da elicitation e estado opaco por Task.
- Escolha inválida mantém a pausa e repete a lista. Uma escolha válida repete o
  `tools/call` original com novo id JSON-RPC, mesma chave em `inputResponses` e
  `requestState` inalterado. Duas Tasks pausadas não podem trocar seus estados.
- `escolha=recusar` vira `action: decline` e `TASK_STATE_CANCELED`.
  No MCP, `decline` e `cancel` concluem com `complete`, sem erro, com
  `reservado: false` e `motivo` no `structuredContent`.
- Sucesso termina em `TASK_STATE_COMPLETED` com artifact `reserva`, contendo o JSON
  da reserva em parte de texto e `politica` com a versão lida do resource.
  Erro de execução da tool termina em `TASK_STATE_FAILED`, com a mensagem exata no histórico.
- `GetTask` deve refletir identidade, estado corrente e artifacts disponíveis.
  Estados `COMPLETED`, `CANCELED` e `FAILED` são definitivos: rejeite novas mensagens
  dirigidas a Tasks terminais.

## Política e erros exatos

- Aplique as mesmas validações na consulta e na reserva: sala existente, intervalo
  com fim posterior ao início, janela 08:00–20:00 de São Paulo (`-03:00`), duração
  máxima de duas horas e ausência de sobreposição. Reservar no passado é permitido.
- Ofereça no máximo três salas livres com capacidade igual ou maior que a solicitada,
  ordenadas por capacidade crescente e, em empate, `id` alfabético.
  Sem alternativas, devolva erro de execução, sem elicitation.
- Erros de domínio são `complete` com `isError: true`. Preserve as mensagens abaixo;
  prefixo adicionado pelo SDK é aceito. Tool inexistente pode gerar `-32602` ou `isError`.

| Condição | Mensagem |
| --- | --- |
| Sala inexistente | `Sala inexistente: <id informado>` |
| Fora da janela | `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00` |
| Duração excessiva | `Duracao acima do limite: a politica permite no maximo 2 horas` |
| Intervalo vazio ou invertido | `Intervalo invalido: fim deve ser posterior a inicio` |
| Sem alternativa | `Sem alternativas disponiveis no intervalo` |

## Validação e entrega

- Implemente primeiro MCP e MRTR, depois o agente como cliente MCP e, por fim,
  A2A e a ponte, conforme a sequência sugerida pelo README.
- Com os dois processos recém-iniciados, execute com Python 3.10+:

  ```bash
  python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
  ```

- Exija as 36 verificações passando e saída 0. Confira também os critérios manuais:
  logs de descoberta e trace-id, retry com id novo, adulteração/expiração do estado,
  argumentos adulterados, retry após restart MCP, capability ausente, escolhas
  inválidas, recusa, erro de domínio, duas Tasks pausadas e estados terminais.
- Documente limitações reais do SDK com evidências no README; não contorne
  reescrevendo o protocolo. Preserve as variações aceitas pelo enunciado entre SDKs.
- Na entrega, substitua o README pelas seções **Como rodar**, **Onde a ponte acontece**,
  **Decisões técnicas** e **Saída do validador**, incluindo a saída completa da última execução.
  Verifique comandos a partir de clone limpo e documente o segredo sem revelar seu valor.
- Entregue o link de um único repositório público, fork do starter, na branch `main`.

## Fora de escopo

Não introduza autenticação/autorização, OAuth, tokens, `securitySchemes` efetivos,
streaming A2A, SSE, push, `SendStreamingMessage`, refinamento ou continuidade entre
Tasks, `referenceTaskIds`, card estendido autenticado, JWS do card, prompts MCP,
subscriptions, progress, containers, compose, deploy, gateway ou interface gráfica.
Persistência em disco das reservas, transações/concorrência de escrita para reservas
no mesmo milissegundo e spans/atributos OpenTelemetry também ficam fora de escopo.
O transporte Streamable HTTP e a propagação/log do `traceparent` continuam obrigatórios.
