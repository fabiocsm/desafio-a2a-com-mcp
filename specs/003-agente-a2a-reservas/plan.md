# Implementation Plan: Agente A2A para descoberta e reservas diretas

**Branch**: `dev` (branch Git real, preservado) | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-agente-a2a-reservas/spec.md`

**Feature context**: `003-agente-a2a-reservas` é o contexto retornado pelo setup; não é um branch Git criado.

## Summary

Criar o processo ponte_agente com rotas e tipos A2A v1 do SDK 1.2.3 e host MCP 2.3.0. Um RequestHandler pequeno mantém Tasks em memória, interpreta o formato fixo e delega a reserva ao servidor MCP real; o SDK preserva envelopes e serialização Protobuf/ProtoJSON.

Abrange o caminho direto, descoberta, artefatos, falhas e rastreamento de FR-001 a FR-015 da spec 003. Não implementar a decisão de conflito nesta etapa; 004 completa a pausa sem resposta automática.

Dependências: 001 para reserva livre; 002 para o contrato interativo que será integrado em 004.

Phase 0 consolidada em [research.md](research.md); Phase 1 detalhada em
[data-model.md](data-model.md), [contrato](contracts/a2a.md) e
[quickstart.md](quickstart.md). A decomposição executável está em [tasks.md](tasks.md);
estes documentos não implementam a aplicação.

## Technical Context

**Language/Version**: Python 3.12+ como baseline do projeto; o requisito mínimo externo é Python 3.10+.

**Primary Dependencies**: mcp==2.3.0, a2a-sdk[http-server]==1.2.3, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0. Fixar também a versão exata do backend de build no pyproject.toml. Não instalar extras all/telemetry/SQL/gRPC/FastAPI.

**Storage**: Mapa de Task pública por taskId em memória do agente; catálogo descoberto e política lida podem ser reutilizados no processo. Nenhuma regra ou reserva local de sala.

**Testing**: unittest/IsolatedAsyncioTestCase e unittest.mock da biblioteca padrão; HTTP real e subprocessos para integração; validador original na aceitação final.

**Target Platform**: Execução local em macOS/Linux, loopback HTTP, um worker por processo; sem container ou deploy.

**Project Type**: Dois serviços HTTP independentes, servidor MCP e agente A2A, sem interface gráfica.

**Performance Goals**: Não há SLA de latência ou throughput no enunciado. Chamadas terminam com resultado ou pausa, sem aguardar decisão humana; escala de cinco salas.

**Constraints**: MCP v2/2026-07-28, A2A v1.0, dois processos, sem LLM, sem sessão de protocolo, arquivos protegidos imutáveis e erros/textos exatos.

**Scale/Scope**: Um Agent Card, SendMessage e GetTask, um cliente MCP reutilizável, Tasks independentes e sem streaming.

### Decisões compartilhadas

Instalar o agente como pacote src separado, usando `python -m ponte_agente`. Configurar AGENTE_HOST=127.0.0.1, AGENTE_PORT=7300, MCP_URL=http://127.0.0.1:7301/mcp e A2A_BASE_URL=http://127.0.0.1:7300 como padrões. O segredo REQUEST_STATE_SECRET pertence apenas ao servidor MCP. Usar Client em mode='2026-07-28' e a sessão de baixo nível para impedir fallback initialize ou auto-resposta MRTR.

## Constitution Check

Gate de entrada: requisitos e restrições constitucionais revisados antes das decisões
específicas. Gate de saída: design revisto após research, modelos e contratos.
A avaliação abaixo é de design; não declara que testes da aplicação passaram.
O gate de FR-008 verifica `elicitation.form` como objeto em cada request MCP.
Capabilities adicionais do SDK, como `elicitation.url`, são permitidas; o gate
não compara o objeto inteiro. A execução dos testes de wire comprova o requisito.

| Princípio | Antes de Phase 0 | Após Phase 1 / evidência de design |
| --- | --- | --- |
| I. Fronteiras e responsabilidade | PASS — requisito preservado | PASS — Host usa HTTP real; nenhuma importação de ponte_mcp nem cálculo de política/alternativas no agente. |
| II. Estado explícito | PASS — requisito preservado | PASS — Metadados/headers por request e Task explícita; T005/T006/T031 verificam form em cada operação, permitindo capabilities adicionais. |
| III. Integridade/opacidade | PASS — requisito preservado | PASS — Sem acesso à chave ou abertura de token; isolamento privado da continuação será concluído na 004. |
| IV. Contratos/determinismo | PASS — requisito preservado | PASS — SDK A2A v1 e parser fixo, sem LLM, modelos/enums atuais e erros preservados. |
| V. Conformidade/rastreio | PASS — requisito preservado | PASS — Descoberta, política, form por request e trace têm testes planejados; a entrega integral continua dependendo da execução dos gates das specs 004/005. |

Há uma divergência normativa do starter: os requests A2A dos exemplos/validador omitem A2A-Version, mas usam métodos v1.0. O SDK exige versão 1.0 no contexto. Usar o ponto público ServerCallContextBuilder para estabelecer 1.0 apenas quando o header estiver ausente em /a2a, preservando versões explícitas e sem ativar compatibilidade 0.3. Documentar esse perfil e sua evidência; não afirmar negociação normativa irrestrita.

A API MCP 2.3.0 anuncia form e url ao registrar elicitation_callback, conforme
evidência em research.md. Esse anúncio atende FR-008 porque inclui form.
Registrar callback defensivo e usar session.call_tool(..., allow_input_required=True)
evita resposta automática. T005/T006/T031 inspecionam form em cada request e
permitem capabilities adicionais. Não usar monkeypatch, atributos privados ou
envelope artesanal; não é necessária troca de pin por esse anúncio.

## Project Structure

### Documentation (this feature)

```text
specs/003-agente-a2a-reservas/
├── spec.md
├── specify-input.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── tasks.md
├── contracts/a2a.md
└── checklists/requirements.md
```

### Source Code (repository root)

Estrutura proposta para implementação; estes arquivos de aplicação não são criados
pelo planejamento. Dados, exemplos e validador permanecem nas posições originais.

```text
agente/
├── pyproject.toml
├── src/ponte_agente/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py          # rotas SDK A2A, card e contexto HTTP
│   ├── handler.py      # SendMessage/GetTask e parser fixo
│   ├── mcp_host.py     # Client moderno, discovery/resource/raw session
│   └── tasks.py        # Task pública, transições e mapa em memória
└── tests/
    ├── test_agente_direto.py # HTTP real e dois processos
    ├── test_mcp_host.py     # sessão raw, discovery, metadata/headers e política
    └── test_tasks.py        # parser, transições, consulta e terminalidade
servidor-mcp/            # outro pacote/processo, sem importação pelo agente
```

**Structure Decision**: Um pacote de agente com quatro módulos de responsabilidade concreta. Usar RequestHandler público do SDK para apenas as duas operações; os demais métodos abstratos retornam UnsupportedOperationError do SDK. Não copiar dispatcher, serialização ou camada de transporte.

### Sequência executável em tasks.md

1. Criar o pacote agente com os pins comuns e entrypoint; abrir/fechar o cliente MCP no lifespan do app, sem iniciar o servidor MCP como subprocesso do agente.
2. Publicar AgentCard com supportedInterfaces, versão 1.0, JSONRPC e skill reservar-sala usando create_agent_card_routes; gerar as rotas com create_jsonrpc_routes(handler, rpc_url='/a2a', enable_v0_3_compat=False).
3. Implementar ServerCallContextBuilder para o perfil do starter e capturar traceparent do request em contexto explícito. Header ausente assume a versão fixa do endpoint; header incompatível não é silenciosamente substituído.
4. Usar tipos Protobuf a2a.types.a2a_pb2, Part(text=...), enums ROLE_* e TASK_STATE_*, deixando o SDK serializar camelCase e envelopes. Não usar TextPart/kind ou classes de aplicação legadas.
5. Fazer descoberta tools/list explícita antes do primeiro tools/call e ler politica://uso. Guardar catálogo e versão obtida como dados de aplicação, nunca como sessão de capabilities.
6. Verificar a presença de elicitation.form como objeto em cada request desde a fundação (T005/T006), permitindo capabilities adicionais anunciadas pelo SDK. Efetuar calls pelo caminho client.session.call_tool(..., allow_input_required=True, meta=trace_meta), com callback defensivo que falha se chamado. Não usar Client.call_tool, que auto-resolve MRTR.
7. Parsear sala/inicio/fim/responsavel no texto fixo e criar Task com UUIDs próprios, SUBMITTED/WORKING e histórico. Nenhuma validação de negócio é repetida antes da resposta MCP.
8. Mapear complete com sucesso para COMPLETED/artifact reserva; isError para FAILED com mensagem original; falha técnica/protocolo após criar Task também vira FAILED, com mensagem `Falha ao executar pedido no servidor MCP` e sem exceção/corpo bruto. GetTask funcional já integra T016 para permitir instanciar o RequestHandler; US2 completa os cenários durante WORKING e de identidade desconhecida. A recusa de envio para terminal acontece antes de MCP. Entrada malformada antes de criar Task usa erro de parâmetro; identidade desconhecida usa TaskNotFound.
9. Testar HTTP entre dois processos, headers/metadata nos requests reais, origem da política, trace-id, terminalidade e GetTask. Preparar o retorno cru input_required para a integração 004, sem inventar sucesso/falha substituto.

### Validação e rastreabilidade

FR-001/002/003: processos, card, rotas e perfil de versão; FR-004/005: parser/identidades/transições; FR-006/007/008/009/010: host, descoberta, resource, metadados, headers e trace; FR-011/012/013/014: artifact, falhas, consulta e terminalidade; FR-015: nenhuma exposição ou resposta automática. Correspondência oficial: 21–26 e 35; terminalidade de 31 é parcialmente verificável nesta feature com Tasks diretas. A sequência oficial de 31 usa retomada, portanto sua execução integral, assim como 27–30/32–34/36, depende de 004. O validador não oferece filtro parcial.

### Cobertura por requisito

Os casos abaixo são validações planejadas, não resultados de testes já executados.

| Requisito da spec | Evidência prevista |
| --- | --- |
| FR-001 | Dois processos e HTTP, sem importação do domínio. |
| FR-002 | Card HTTP200, interface v1 e skill correta. |
| FR-003 | SendMessage/GetTask em /a2a com porta padrão. |
| FR-004 | Identidade própria e SUBMITTED/WORKING antes do resultado. |
| FR-005 | Parser fixo, determinismo e ausência de LLM. |
| FR-006 | tools/list observado antes do primeiro tools/call. |
| FR-007 | Política extraída do resource e versão no artifact. |
| FR-008 | T005/T006/T031: metadata moderna e elicitation.form como objeto em cada request; capabilities adicionais permitidas. |
| FR-009 | Headers espelhados pelo SDK em cada chamada. |
| FR-010 | Trace-id do A2A aparece no MCP; contexto isolado por Task. |
| FR-011 | Task COMPLETED e artifact reserva com JSON correto. |
| FR-012 | isError vira FAILED com texto exato da tool. |
| FR-013 | GetTask preserva identidade/estado/artifacts. |
| FR-014 | SendMessage em terminal não reabre nem chama MCP. |
| FR-015 | Raw input_required sem auto-resposta nem exposição; integração na 004. |

### Riscos e limites

Usar nomes de classes da linha A2A 0.3 gera envelopes errados. O SDK atual devolve GetTask como Task direta; o validador aceita essa forma e o wrapper do exemplo, então não modificar o SDK para imitar o exemplo. Meta de trace deve ser montada por chamada, sem mutar configuração global do cliente. Não é necessário implementar LLM, banco, SSE ou autenticação porque o SDK os oferece como extras.

## Complexity Tracking

Sem exceções de complexidade propostas. O anúncio form+url do pin MCP atende
FR-008; os testes verificam form por request, sem proibir capabilities adicionais.
O perfil A2A está documentado em research.md e no contrato. Não alterar SDKs,
arquivos protegidos ou regras do desafio. Não há camada
de serviços, repositório abstrato, banco, autenticação ou instrumentação adicional.
