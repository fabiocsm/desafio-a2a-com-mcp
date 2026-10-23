# Implementation Plan: Conformidade, reprodução e documentação da entrega

**Branch**: `dev` (branch Git real, preservado) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-conformidade-entrega/spec.md`

**Feature context**: `005-conformidade-entrega` é o contexto retornado pelo setup; não é um branch Git criado.

## Summary

Concluir a entrega com instalação reproduzível, comandos de dois processos, execução integral do validador e cenários adicionais de evidência. Atualizar o README somente durante a implementação desta feature, usando resultados reais da revisão entregue.

Abrange FR-001 a FR-014 da spec 005 e a rastreabilidade dos 37 critérios no índice SDD. Não cria novo comportamento de reserva; falhas encontradas devem ser corrigidas na capacidade responsável das features 001–004.

Dependências: 001, 002, 003 e 004 implementadas e verificadas.

**Gate herdado de capabilities**: a 003 verifica `elicitation.form` como objeto
em cada request MCP. Capabilities adicionais, como `elicitation.url`, são permitidas
e não bloqueiam a 005. A aceitação depende dos testes de wire e dos demais critérios
da entrega; manter os pins exatos efetivamente validados nos manifests e constraints.

Phase 0 consolidada em [research.md](research.md); Phase 1 detalhada em
[data-model.md](data-model.md), [contrato](contracts/entrega.md) e
[quickstart.md](quickstart.md). A execução está decomposta em [tasks.md](tasks.md),
gerado depois do design; nenhum desses artefatos declara código ou testes executados.

## Technical Context

**Language/Version**: Python 3.12+ como baseline do projeto; o requisito mínimo externo é Python 3.10+.

**Primary Dependencies**: Pins de base: mcp==2.3.0, a2a-sdk[http-server]==1.2.3, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3, pydantic==2.12.0. A aprovação funcional exige os testes de wire de 003/FR-008, com form por request e capabilities adicionais permitidas; qualquer revisão de dependências deve ser exata e validada antes das constraints. Ferramentas de evidência usam biblioteca padrão.

**Storage**: Somente evidências de execução e arquivo de constraints versionado, sem banco. Estado temporário de um teste MRTR fica fora do repositório; segredo não é artefato de entrega.

**Testing**: unittest/IsolatedAsyncioTestCase e unittest.mock da biblioteca padrão; HTTP real e subprocessos para integração; validador original na aceitação final.

**Target Platform**: Execução local em macOS/Linux, loopback HTTP, um worker por processo; sem container ou deploy.

**Project Type**: Dois serviços HTTP independentes, servidor MCP e agente A2A, sem interface gráfica.

**Performance Goals**: Não há SLA de latência ou throughput no enunciado. Chamadas terminam com resultado ou pausa, sem aguardar decisão humana; escala de cinco salas.

**Constraints**: MCP v2/2026-07-28, A2A v1.0, dois processos, sem LLM, sem sessão de protocolo, arquivos protegidos imutáveis e erros/textos exatos.

**Scale/Scope**: 36 verificações oficiais, 37 critérios de aceite mapeados, quatro seções obrigatórias no README e uma reprodução em clone limpo.

### Decisões compartilhadas

Fixar dependências diretas nos dois pyproject.toml e registrar a resolução completa em constraints.txt gerado a partir de ambiente limpo, excluindo os pacotes editáveis. Não adicionar CI/deploy/containers. A versão Python escolhida é 3.12+; o validador original segue sem dependências externas. Preservar o mesmo segredo e nome MCP ao testar restart.

## Constitution Check

Gate de entrada: requisitos e restrições constitucionais revisados antes das decisões
específicas. Gate de saída: design revisto após research, modelos e contratos.
A aprovação abaixo é de design; não declara que testes da aplicação passaram.

| Princípio | Antes de Phase 0 | Após Phase 1 / evidência de design |
| --- | --- | --- |
| I. Fronteiras e responsabilidade | PASS — requisito preservado | PASS — Comandos sobem dois processos independentes; scripts de apoio não fundem os serviços. |
| II. Estado explícito | PASS — requisito preservado | PASS — Exigir form em cada request e testes de wire aprovados, permitindo capabilities adicionais; pausa/retry/restart previstos sem sessão. |
| III. Integridade/opacidade | PASS — requisito preservado | PASS — Chave gerada localmente, TTL 600 e AEAD documentados; tokens temporários excluídos das evidências públicas. |
| IV. Contratos/determinismo | PASS — requisito preservado | PASS — Validador original e arquivos protegidos comparados com baseline; nenhuma saída fabricada. |
| V. Conformidade/rastreio | PASS — requisito preservado | PASS — 36 PASS reais, logs, testes de wire e testes manuais são gates previstos para a execução da entrega. |

A aprovação de design não substitui a execução futura. README e evidências só podem afirmar 36 PASS depois da execução com os processos recém-iniciados. Limitações comprovadas do SDK e o perfil de versão A2A serão documentados explicitamente; nenhum critério ausente será marcado como atendido por uma ressalva.

## Project Structure

### Documentation (this feature)

```text
specs/005-conformidade-entrega/
├── spec.md
├── specify-input.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
├── contracts/entrega.md
└── checklists/requirements.md
```

### Source Code (repository root)

Estrutura proposta para implementação; estes arquivos de aplicação não são criados
pelo planejamento. Dados, exemplos e validador permanecem nas posições originais.

```text
constraints.txt                    # resolução completa, sem paths editáveis locais
README.md                          # quatro seções exigidas, na implementação
scripts/
└── verificar_entrega.py            # provas adicionais HTTP e suporte ao restart manual
tests/
└── test_entrega.py                 # contratos de empacotamento/configuração
docs/evidencias/
├── validador.txt                   # saída integral real da última execução
└── manual.md                       # cenário, revisão e resultado observável
servidor-mcp/                       # preserva pacote próprio
agente/                             # preserva pacote próprio
dados/, exemplos/, validador/       # protegidos, sem alterações
```

**Structure Decision**: Adicionar somente suporte de validação e evidência ao repositório. O verificador adicional usa HTTP e processos reais, sem importar regras de sala nem alterar o validador. Evidências versionadas não contêm segredo ou token de continuação.

### Sequência de implementação a detalhar em tasks.md

1. Consolidar os pins já escolhidos nos manifests e gerar constraints.txt em .venv limpa com pip freeze --exclude-editable; confirmar instalação dos dois pacotes a partir de clone limpo com essas constraints.
2. Definir os comandos documentados de startup, host/porta/baseURL e geração/exportação de REQUEST_STATE_SECRET. Rodar os serviços em terminais separados e manter stderr MCP visível.
3. Preparar scripts/verificar_entrega.py apenas para as provas que não são suficientes na suíte original, incluindo emissão/retomada de estado com restart manual no meio, rastreamento e privacidade.
4. Conferir que arquivos protegidos continuam iguais à base original do fork, usando comparação de Git ou hashes contra a referência inicial, sem restaurar/sobrescrever arquivos automaticamente.
5. Executar os testes das quatro capacidades em bases controladas e corrigir falhas na feature responsável; não modificar casos do validador para obter PASS.
6. Reiniciar ambos os processos e executar o comando oficial integral; salvar stdout/stderr e código de saída reais, sem deixar pipe para tee ocultar o status.
7. Separadamente, com base limpa, executar o fluxo manual e registrar descoberta, trace-id, ids distintos, restart, adulteração/expiração, recusa, escolha inválida, duas Tasks e terminalidade.
8. Atualizar README com as quatro seções, pontos reais do código da ponte, AES-256-GCM/TTL600, armazenamento de Tasks, pins, capabilities observadas e perfil de versão. Colar a última saída completa real do validador.
9. Conferir o fork público único, estrutura e branch main da entrega final; reproduzir os comandos em clone limpo antes do push final. Este plano não executa push nem altera branches.

### Validação e rastreabilidade

FR-001/002/003: clone limpo, pins, comandos e segredo; FR-004: 36 verificações e saída; FR-005/006/007: evidências manuais; FR-008/009/010: README e resultados fiéis; FR-011/012: integridade da árvore/fork/main/ausência LLM; FR-013/014: limitações documentadas e escopo. O índice specs/README.md mantém o mapa de todos os critérios e aponta a feature funcional responsável.

As provas adicionais têm responsabilidades distintas: o script cobre restart manual,
rastreamento e fluxos públicos/privacidade. A suíte `servidor-mcp/tests/test_mrtr.py`
da 002 comprova integridade, expiração, argumentos e capability com HTTP real;
o relógio controlado fica no servidor isolado do teste, mantendo TTL 600 de produção.
Argumentos adulterados podem ser rejeitados ou substituídos pelos valores selados,
conforme a constituição; nenhuma reserva pode usar valores adulterados. Testes de
serialização da 004 complementam a inspeção HTTP com tokens sentinela conhecidos.
Mocks do suporte não são evidência de execução dos protocolos.

Cada cenário mutante do script começa com os dois processos reiniciados e log
externo próprio. A exceção é a transição emitir → retomar do cenário de restart:
somente o MCP reinicia, preservando chave e audience. O caso rastreamento inicia
seu próprio fluxo A2A em agente limpo e usa trace-id exclusivo; a evidência da suíte
oficial preserva separadamente o trace-id impresso pelo validador e a descoberta
do agente, sem atribuir a ele requests do cliente direto do validador.

A última reprodução em clone limpo fornece a saída final a transcrever no README.
Todos os arquivos de evidência são concluídos antes do push; a conferência pública
posterior apenas verifica a main e informa seu hash/link, sem edição local pendente.

### Cobertura por requisito

Os casos abaixo são validações planejadas, não resultados de testes já executados.

| Requisito da spec | Evidência prevista |
| --- | --- |
| FR-001 | Comandos verificados em clone limpo. |
| FR-002 | Pins, constraints e pip check em ambiente limpo. |
| FR-003 | Geração/exportação do segredo sem publicação do valor. |
| FR-004 | 36 PASS, zero FAIL e status 0 com processos recém-iniciados. |
| FR-005 | Evidência de descoberta/trace/ids em stderr. |
| FR-006 | Manuais de restart, integridade, expiração, argumentos e capability. |
| FR-007 | Matriz de fluxos A2A e busca de vazamento. |
| FR-008 | Quatro seções README e referências reais ao código. |
| FR-009 | Decisões reais AES-GCM, TTL de 600 segundos e Tasks em memória. |
| FR-010 | Saída completa real da última execução da versão entregue. |
| FR-011 | Comparação dos protegidos com base original e dois processos. |
| FR-012 | Revisão de fork único/público/main e ausência LLM/segredo. |
| FR-013 | Limitações com evidência e sem alteração dos SDKs. |
| FR-014 | Revisão de exclusões: sem infra, persistência, auth, GUI ou telemetria. |

### Riscos e limites

O validador muda reservas: toda nova rodada começa com ambos os processos reiniciados. Os cenários manuais também alteram estado e não devem reutilizar uma base já consumida pela suíte. pip freeze de ambiente contaminado ou com paths locais não produz constraints portáveis. Não afirmar que metadados de versão ou pip dry-run equivalem a testes de runtime. A publicação na main pertence à execução da entrega, não ao planejamento.

## Complexity Tracking

Sem exceções de complexidade propostas. O gate 003/FR-008 verifica form por
request e permite capabilities adicionais, como url. A execução da 005 exige
testes de wire aprovados e os demais critérios de entrega. O perfil A2A está
documentado em research.md e no contrato; não alterar SDKs, arquivos protegidos
ou regras do desafio. Não há camada de
serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
