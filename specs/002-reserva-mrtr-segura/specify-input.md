# Entrada para $speckit-specify — Reserva com alternativas e retomada MRTR segura

Diretório de destino: `specs/002-reserva-mrtr-segura`.
Texto utilizado nesta geração; reutilize como contexto ao revisar esta feature,
sem criar outra feature com o mesmo escopo.

```text
$speckit-specify
Especifique a negociação de reserva em conflito no servidor MCP, complementando 001-servidor-mcp-salas. Quando houver conflito, calcule até três salas livres de capacidade igual ou maior, ordenadas por capacidade e id, e responda input_required com uma única elicitation em form mode e requestState. A escolha é restrita ao schema; uma alternativa pode usar enum ou const. Sem alternativa, devolva o erro exato Sem alternativas disponiveis no intervalo. Exija a capability de form elicitation por request e use -32021/HTTP 400/data.requiredCapabilities quando faltar. O estado deve ter integridade HMAC ou AEAD, expiração entre 5 e 30 minutos e chave REQUEST_STATE_SECRET com pelo menos 32 bytes de aleatoriedade. O retry usa novo id, inputResponses com a chave original e requestState em params; deve funcionar após restart do MCP sem memória de continuação, usando a mesma chave. Rejeite estado adulterado/expirado com -32602 e impeça que argumentos reenviados adulterados mudem o pedido selado. Decline/cancel concluem sem erro e sem reserva, com reservado false e motivo. Esta spec trata do contrato MCP direto; o armazenamento por Task e a pausa A2A pertencem à spec 004. Respeite AGENTS.md e .specify/memory/constitution.md. Preserve dados/, validador/ e exemplos/ sem alterações, dois processos separados por HTTP, ausência de sessão de protocolo e de LLM, formatos e mensagens exatos e o escopo fechado do README. Use os exemplos completos de wire como contratos. A especificação deve definir comportamento e critérios verificáveis, sem escolher linguagem, SDK entre as alternativas permitidas ou arquitetura interna. Não implemente código nem gere plano ou tarefas nesta etapa.
```
