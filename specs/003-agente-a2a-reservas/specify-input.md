# Entrada para $speckit-specify — Agente A2A para descoberta e reservas diretas

Diretório de destino: `specs/003-agente-a2a-reservas`.
Texto utilizado nesta geração; reutilize como contexto ao revisar esta feature,
sem criar outra feature com o mesmo escopo.

```text
$speckit-specify
Especifique o agente do desafio como servidor A2A v1.0 e host MCP para o caminho de reserva direta, consumindo o servidor real da spec 001 por HTTP. Publique o card em /.well-known/agent-card.json, porta padrão 7300, com interface JSON-RPC em /a2a, versão 1.0 e skill reservar-sala. Aceite SendMessage e GetTask, crie id e contextId próprios e passe por SUBMITTED e WORKING. Interprete somente reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>, sem LLM. Descubra ferramentas por tools/list antes da primeira chamada, sem lista fixa, leia a versão de politica://uso e envie metadados, capability form e headers espelhados em cada request MCP. Propague o trace-id A2A nos requests MCP da Task. Sucesso produz COMPLETED e artifact reserva em parte de texto com o JSON e versão da política; isError da tool produz FAILED com a mensagem exata no histórico. Estados terminais não reabrem. A pausa e a retomada de conflitos serão definidas em 004-ponte-a2a-mrtr; não responda automaticamente a elicitation nem exponha requestState. Respeite AGENTS.md e .specify/memory/constitution.md. Preserve dados/, validador/ e exemplos/ sem alterações, dois processos separados por HTTP, ausência de sessão de protocolo e de LLM, formatos e mensagens exatos e o escopo fechado do README. Use os exemplos completos de wire como contratos. A especificação deve definir comportamento e critérios verificáveis, sem escolher linguagem, SDK entre as alternativas permitidas ou arquitetura interna. Não implemente código nem gere plano ou tarefas nesta etapa.
```
