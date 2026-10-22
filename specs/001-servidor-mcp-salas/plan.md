# Implementation Plan: Servidor MCP de salas e reservas diretas

**Branch**: `dev` (branch Git real, preservado) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-servidor-mcp-salas/spec.md`

**Feature context**: `001-servidor-mcp-salas` é o contexto retornado pelo setup; não é um branch Git criado.

## Summary

Construir o serviço de salas com MCPServer do SDK oficial Python 2.3.0, transporte Streamable HTTP moderno e funções pequenas para catálogo, política, disponibilidade e reserva livre. O mesmo estado de reservas em memória atende todas as chamadas do processo.

Esta feature entrega FR-001 a FR-014 da spec e prepara a continuação de FR-015 pela feature 002. Não define uma resposta provisória incompatível para conflitos nem implementa o agente.

Dependências: nenhuma feature anterior; a feature 002 completa a reserva com conflito.

Phase 0 consolidada em [research.md](research.md); Phase 1 detalhada em
[data-model.md](data-model.md), [contrato](contracts/mcp.md) e
[quickstart.md](quickstart.md). A decomposição executável posterior está em
[tasks.md](tasks.md); estes artefatos documentais não implementam a aplicação.

## Technical Context

**Language/Version**: Python 3.12+ como baseline do projeto; o requisito mínimo externo é Python 3.10+.

**Primary Dependencies**: mcp==2.3.0, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0. Fixar também o backend de build no pyproject.toml. A2A só entra no pacote do agente em 003.

**Storage**: JSON originais somente leitura; lista/dicionário de reservas e contador de ids no processo; nenhuma gravação em dados/.

**Testing**: unittest/IsolatedAsyncioTestCase e unittest.mock da biblioteca padrão; HTTP real e subprocessos para integração; validador original na aceitação final.

**Target Platform**: Execução local em macOS/Linux, loopback HTTP, um worker por processo; sem container ou deploy.

**Project Type**: Dois serviços HTTP independentes, servidor MCP e agente A2A, sem interface gráfica.

**Performance Goals**: Não há SLA de latência ou throughput no enunciado. Chamadas terminam com resultado ou pausa, sem aguardar decisão humana; escala de cinco salas.

**Constraints**: MCP v2/2026-07-28, A2A v1.0, dois processos, sem LLM, sem sessão de protocolo, arquivos protegidos imutáveis e erros/textos exatos.

**Scale/Scope**: Cinco salas, três tools, um resource e validação direta do contrato MCP; sem metas artificiais de carga.

### Decisões compartilhadas

Adotar Python 3.12+ para os dois pacotes. Cada processo terá pyproject.toml próprio e pacote src instalável em uma .venv compartilhada de desenvolvimento; nenhum processo importa código de domínio do outro. Expor `python -m ponte_mcp` e, futuramente, `python -m ponte_agente`. Fixar os pins acima nos manifestos, incluindo dependências usadas diretamente, sem extras cli/all/telemetry. A presença transitiva de bibliotecas SSE ou OpenTelemetry não habilita esses recursos de produto.

## Constitution Check

Gate de entrada: requisitos e restrições constitucionais revisados antes das decisões
específicas. Gate de saída: design revisto após research, modelos e contratos.
A aprovação abaixo é de design; não declara que testes da aplicação passaram.

| Princípio | Antes de Phase 0 | Após Phase 1 / evidência de design |
| --- | --- | --- |
| I. Fronteiras e responsabilidade | PASS — requisito preservado | PASS — Somente ponte_mcp conhece os JSON, as regras e as reservas; acesso futuro do agente será HTTP. |
| II. Estado explícito | PASS — requisito preservado | PASS — ASGI stateless e metadados obrigatórios por request; nenhum initialize, cookie ou sessão herdada para o perfil moderno. |
| III. Integridade/opacidade | PASS — requisito preservado | PASS — Configuração estável do segredo preparada para 002, sem chave efêmera implícita em produção da solução. |
| IV. Contratos/determinismo | PASS — requisito preservado | PASS — Modelos tipados e mensagens fixas; arquivos protegidos apenas lidos, sem LLM. |
| V. Conformidade/rastreio | PASS — requisito preservado | PASS — Log externo ao dispatcher e integração HTTP para verificar também requests rejeitados. |

Adaptação necessária: o SDK roteia requests sem MCP-Protocol-Version para o caminho legado. O perfil do desafio não aceita inferir metadados. A borda deve verificar apenas presença dos dois campos obrigatórios de params._meta antes de delegar ao SDK, devolver o erro oficial tipado -32602/HTTP 400 quando faltarem e registrar a requisição. Não inferir versão do header ou de outra chamada. Transporte, espelhamento de headers, despacho, schemas e MRTR continuam no SDK; não copiar seu classificador nem modificar a dependência. A evidência e o teste de ausência simultânea de header/envelope entram na documentação da entrega.

## Project Structure

### Documentation (this feature)

```text
specs/001-servidor-mcp-salas/
├── spec.md
├── specify-input.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/mcp.md
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

Estrutura proposta para implementação; estes arquivos de aplicação não são criados
pelo planejamento. Dados, exemplos e validador permanecem nas posições originais.

```text
servidor-mcp/
├── pyproject.toml
├── src/ponte_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py          # registro SDK, app ASGI e configuração
│   ├── entrada.py      # observação ASGI e guarda estrita de metadados
│   ├── modelos.py      # modelos de entrada/saída e schemas
│   └── salas.py        # funções de catálogo, política e reservas em memória
└── tests/
    ├── test_salas.py
    └── test_mcp_http.py
dados/                 # intocado
exemplos/              # intocado
validador/             # intocado
```

**Structure Decision**: Um pacote de aplicação dentro de servidor-mcp/, com registro SDK separado de funções de domínio e da observação HTTP. Sem camada de serviços, ORM ou interfaces abstratas. Resolver dados/ a partir do repositório identificado pelo arquivo instalado em modo editável, sem depender do cwd do processo.

### Sequência executável em tasks.md

1. Setup: criar pacote instalável, manifesto com versões exatas e suporte unittest/HTTP real.
2. Fundação: definir modelos Pydantic, carregar dados originais uma vez por processo e implementar validação compartilhada com testes. Converter datetimes com timezone para -03:00 e validar a janela no mesmo dia; usar precedência sala, intervalo, janela, duração para entradas de formato válido.
3. Ainda na fundação, construir MCPServer `ponte-salas` e app oficial `streamable_http_app(streamable_http_path='/mcp', json_response=True, stateless_http=True, host=host)`; servir em um worker com lifespan intacto. Envolver a entrada com observação ASGI e guarda de presença usando JSONRPCError/ErrorData oficiais, sem alterar o body ou despachar tools/MRTR. Configurar MCP_HOST=127.0.0.1/MCP_PORT=7301 e overrides, e validar REQUEST_STATE_SECRET hexadecimal com pelo menos 32 bytes decodificados. A proteção MRTR é completada na 002, com nome/audience estável e sem chave efêmera como desenho final.
4. US2 (P1): implementar consulta e reserva livre, interseção `inicio < reserva.fim e fim > reserva.inicio`, registrar os dois handlers reais e verificar atualização da disponibilidade e restart. Este é o MVP de reserva direta, verificável sem agente, listar_salas ou resource publicado.
5. US1 (P1): implementar catálogo e resource, registrar listar_salas e verificar a descoberta integral das três tools, schemas, equivalência de JSON, política e erros de tool/URI inexistente. A US2 precede esta história de mesma prioridade para que o teste independente de descoberta encontre handlers reais, sem stubs ou contrato temporário.
6. US3 (P2): completar matriz de erros de domínio/protocolo, mensagens exatas, metadados/headers e logs, preservando as alternativas oficiais de erro do SDK.
7. Executar a regressão, os comandos do quickstart em ambiente novo e a revisão dos cinco princípios; passar a base utilizável para 002. As histórias mantêm os identificadores da spec, com dependências explícitas US2 → US1 → US3.

### Validação e rastreabilidade

FR-001/002/003/004: descoberta e comparação de schemas/JSONs; FR-005/006/007/008: catálogo inicial, intervalos válidos e atualização de disponibilidade; FR-009/010/011: mensagens e categorias de erro; FR-012/013/014: metadados, headers e stderr. FR-015 é uma fronteira de escopo completada em 002. As verificações oficiais 01–12 correspondem à base, mas o validador não tem filtro e só será executado integralmente após 004. Usar testes locais específicos até lá.

### Cobertura por requisito

Os casos abaixo são validações planejadas, não resultados de testes já executados.

| Requisito da spec | Evidência prevista |
| --- | --- |
| FR-001 | Endpoint /mcp e porta padrão em teste HTTP. |
| FR-002 | tools/list e capabilities declaradas. |
| FR-003 | Schemas de objeto e outputSchema descobertos. |
| FR-004 | Comparação structuredContent com JSON textual e catálogo original. |
| FR-005 | Reserva criada aparece na consulta seguinte; restart recarrega base. |
| FR-006 | Matriz de sala, janela no mesmo dia, duração, intervalo, passado, limites, timezone obrigatório e offsets equivalentes. |
| FR-007 | Consulta de conflitos não grava reservas. |
| FR-008 | Reserva livre completa com todos os campos. |
| FR-009 | Quatro erros exatos em consulta e reserva e precedência sala/intervalo/janela/duração nas violações simultâneas de domínio. |
| FR-010 | Resource integral, MIME correto e URI inexistente. |
| FR-011 | Tool inexistente recusada pela alternativa permitida. |
| FR-012 | Metadata ausente com/sem header e sem herança. |
| FR-013 | Headers divergentes geram -32020. |
| FR-014 | stderr inclui método/id/trace também para rejeições. |
| FR-015 | Fronteira de conflito completada pela 002; sem contrato substituto. |

### Riscos e limites

Sem header moderno o SDK tem roteamento legado: cobertura deve incluir metadados ausentes com e sem header, não apenas o caso do validador. A observação não pode consumir o body ou o lifespan. Testes não podem assumir o id ilustrativo res-0003, apenas identidade própria e conteúdo correto. Intervalos adjacentes não conflitam; datas passadas não são rejeitadas.

## Complexity Tracking

Sem violações constitucionais ou exceções de complexidade. As adaptações de perfil
necessárias ao wire do starter estão documentadas em research.md e no contrato;
não alteram SDKs, arquivos protegidos ou as regras do desafio. Não há camada de
serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
