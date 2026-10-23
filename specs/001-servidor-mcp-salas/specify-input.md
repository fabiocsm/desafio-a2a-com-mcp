# Entrada para $speckit-specify — Servidor MCP de salas e reservas diretas

Diretório de destino: `specs/001-servidor-mcp-salas`.
Texto utilizado nesta geração; reutilize como contexto ao revisar esta feature,
sem criar outra feature com o mesmo escopo.

```text
$speckit-specify
Especifique a capacidade básica de salas do desafio A Ponte para consumidores MCP. O servidor deve publicar tools listar_salas, consultar_disponibilidade e reservar_sala e o resource politica://uso, atender Streamable HTTP em /mcp na porta padrão 7301, declarar capabilities e schemas, devolver dados estruturados e texto equivalentes, carregar dados do starter e tornar novas reservas visíveis no processo. A consulta e a reserva aplicam sala existente, janela 08:00–20:00 de São Paulo (-03:00), duração máxima de duas horas, fim posterior ao início e conflitos; datas passadas são aceitas. Preserve as mensagens exatas de erro, rejeições de metadados obrigatórios ausentes e headers divergentes, e registre método, id e traceparent em stderr. Esta feature cobre reserva em sala livre e consulta de conflitos; a negociação de alternativas e a retomada de reserva em conflito serão especificadas separadamente em 002-reserva-mrtr-segura, sem inventar um comportamento provisório incompatível. Não inclui o agente A2A. Respeite AGENTS.md e .specify/memory/constitution.md. Preserve dados/, validador/ e exemplos/ sem alterações, dois processos separados por HTTP, ausência de sessão de protocolo e de LLM, formatos e mensagens exatos e o escopo fechado do README. Use os exemplos completos de wire como contratos. A especificação deve definir comportamento e critérios verificáveis, sem escolher linguagem, SDK entre as alternativas permitidas ou arquitetura interna. Não implemente código nem gere plano ou tarefas nesta etapa.
```
