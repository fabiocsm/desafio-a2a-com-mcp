# Entrada para $speckit-specify — Conformidade, reprodução e documentação da entrega

Diretório de destino: `specs/005-conformidade-entrega`.
Texto utilizado nesta geração; reutilize como contexto ao revisar esta feature,
sem criar outra feature com o mesmo escopo.

```text
$speckit-specify
Especifique a entrega verificável do desafio A Ponte após as specs 001 a 004. O avaliador deve clonar o fork público, gerar e exportar REQUEST_STATE_SECRET sem obter um segredo publicado, instalar versões travadas e iniciar dois processos em terminais separados seguindo somente o README. Execute o validador original com os dois processos recém-iniciados e exija 36 PASS, nenhum FAIL e código de saída 0; não invente saída nem altere o validador. Além disso, produza evidências manuais de descoberta antes da chamada, mesmo trace-id do A2A até stderr MCP, retry com id novo, estado adulterado/expirado e argumentos divergentes, retry após restart MCP, capability ausente, escolhas inválidas, recusa, erro de domínio, isolamento de Tasks e estados terminais. O README final deve ter Como rodar, Onde a ponte acontece com pontos reais do código, Decisões técnicas com proteção/prazo do estado e armazenamento das Tasks, e Saída do validador com a última saída completa real. Preserve a estrutura e os arquivos protegidos e entregue um único fork público na main. Não adicione container, deploy, GUI, autenticação, banco de dados ou observabilidade além do exigido. Respeite AGENTS.md e .specify/memory/constitution.md. Preserve dados/, validador/ e exemplos/ sem alterações, dois processos separados por HTTP, ausência de sessão de protocolo e de LLM, formatos e mensagens exatos e o escopo fechado do README. Use os exemplos completos de wire como contratos. A especificação deve definir comportamento e critérios verificáveis, sem escolher linguagem, SDK entre as alternativas permitidas ou arquitetura interna. Não implemente código nem gere plano ou tarefas nesta etapa.
```
