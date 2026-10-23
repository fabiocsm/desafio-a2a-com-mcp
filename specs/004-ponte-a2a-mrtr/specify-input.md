# Entrada para $speckit-specify — Ponte A2A–MRTR com pausa e retomada por Task

Diretório de destino: `specs/004-ponte-a2a-mrtr`.
Texto utilizado nesta geração; reutilize como contexto ao revisar esta feature,
sem criar outra feature com o mesmo escopo.

```text
$speckit-specify
Especifique a ponte completa entre a negociação MCP de 002-reserva-mrtr-segura e o agente A2A de 003-agente-a2a-reservas. Um SendMessage de sala ocupada deve chegar ao servidor real, receber input_required e pausar a Task em TASK_STATE_INPUT_REQUIRED com a linha exata alternativas: <ids separados por virgula e espaco>, na ordem do schema, inclusive const com uma opção. Guarde por Task o pedido original, a chave da pergunta, as alternativas e o requestState opaco sem abri-lo, interpretá-lo ou expô-lo. Uma continuação com o mesmo taskId e escolha=<id> deve reenviar o tools/call original com id JSON-RPC novo, inputResponses com a chave original e requestState inalterado. Escolha inválida mantém a pausa e repete a mesma lista. escolha=recusar vira decline, conclui a negociação sem reserva e termina CANCELED. Sucesso termina COMPLETED com o artifact exigido; isError termina FAILED com o texto da tool. GetTask deve refletir a pausa e os resultados; nenhum estado terminal pode reabrir. Demonstre isolamento de duas Tasks pausadas, determinismo de pausas iguais sem mudança de disponibilidade e propagação do trace-id em todas as chamadas da Task, inclusive após continuação sem novo traceparent. Respeite AGENTS.md e .specify/memory/constitution.md. Preserve dados/, validador/ e exemplos/ sem alterações, dois processos separados por HTTP, ausência de sessão de protocolo e de LLM, formatos e mensagens exatos e o escopo fechado do README. Use os exemplos completos de wire como contratos. A especificação deve definir comportamento e critérios verificáveis, sem escolher linguagem, SDK entre as alternativas permitidas ou arquitetura interna. Não implemente código nem gere plano ou tarefas nesta etapa.
```
