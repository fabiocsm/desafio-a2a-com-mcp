# Tasks: Conformidade, reprodução e documentação da entrega

**Input**: `specs/005-conformidade-entrega/` — spec.md, plan.md, research.md, data-model.md, contracts/entrega.md e quickstart.md.
**Prerequisites**: Ler `README.md`, `AGENTS.md`, `.specify/memory/constitution.md`, todos os JSON de `exemplos/wire/` e o mapa AC-001–AC-037 de `specs/README.md`. As capacidades 001 → 002 → 003 → 004 devem estar implementadas e verificadas antes da execução desta lista; isso inclui aprovar o teste de wire de 003/FR-008 com form em cada request, permitindo capabilities adicionais como url.
**Tests**: A spec exige validação oficial e cenários adicionais verificáveis. Usar unittest/unittest.mock existentes e HTTP real, sem framework adicional. Testar o suporte de entrega novo antes de implementá-lo; executar as suítes das features anteriores como regressão, sem duplicar suas regras ou fabricar falhas iniciais.
**Organization**: US1 (P1) → US2 (P1) → US3 (P2), com gates de estado limpo. Todos os checkboxes representam trabalho futuro; gerar esta lista não executa testes da aplicação, altera o README final ou publica o fork.

## Formato e caminhos

- Formato: `- [ ] Tnnn [P?] [USn?] descrição com caminho`.
- Caminhos são relativos à raiz. `[P]` permite somente o grupo de tarefas com arquivos distintos indicado nas dependências, depois de seus pré-requisitos.
- `dados/`, `validador/` e `exemplos/` são somente leitura. Não restaurar nem sobrescrever esses arquivos para ocultar divergências.
- Arquivos de evidência: `docs/evidencias/validador.txt` e `docs/evidencias/manual.md`. Logs brutos e estado temporário permanecem fora do repositório.
- Não criar modelos de domínio ou endpoints novos: esta feature demonstra as capacidades 001–004. Falhas funcionais exigem correção na capacidade responsável, registro de sua FR de origem e nova validação aplicável antes de avançar.

## Phase 1: Setup — inventário e evidência segura

**Objetivo**: Preparar rastreabilidade sem declarar resultados ainda não executados.

- [ ] T001 Criar em `docs/evidencias/manual.md` o inventário de AC-001–AC-037 e FR-001–FR-014/SC-001–SC-005 da 005, com referência à spec/FR funcional responsável, baseline Git original do starter e estado inicialmente pendente; cada registro deve conter literalmente os campos de `data-model.md`: "Revisão/estado de código testado, versão Python e versões diretas instaladas", "Pré-condições, processos reiniciados e intervalo/sala usados", "Comando ou cenário de teste e resultado observado", "Critério de aceite e FR da spec de origem" e "Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva" (FR-004–007/011; SC-002/003/005).
- [ ] T002 Ajustar `.gitignore` para excluir artefatos locais de instalação, logs brutos e caches adicionais gerados pela reprodução; manter `constraints.txt` e `docs/evidencias/` versionáveis e exigir arquivos de continuação criados por mktemp fora da árvore, sem segredo/token publicado ou novo mecanismo de configuração secreta (FR-003/012; SC-004).

**Checkpoint**: Baseline original identificado de forma verificável, não apenas HEAD local; nenhuma evidência marcada como sucesso sem execução.

## Phase 2: Foundational — gate das capacidades e suporte HTTP

**Objetivo**: Bloquear a entrega enquanto suas dependências ou fronteiras não funcionarem.

- [ ] T003 Preparar uma venv com instalação editável dos manifests existentes das features 001–004 e executar as suítes existentes de `servidor-mcp/tests/test_salas.py`, `servidor-mcp/tests/test_mcp_http.py`, `servidor-mcp/tests/test_mrtr.py`, `agente/tests/test_agente_direto.py`, `agente/tests/test_mcp_host.py`, `agente/tests/test_tasks.py` e `agente/tests/test_ponte.py`; exigir aprovação de 003/FR-008 com `elicitation.form` como objeto em cada request, permitindo capabilities adicionais; registrar comandos, resultados e pendências em `docs/evidencias/manual.md`, verificando MCP/MRTR/host/A2A/ponte separadamente; corrigir eventuais falhas nos arquivos da feature responsável antes de avançar, preservando os cinco princípios e os 11 contratos de `exemplos/wire/` (FR-004–007/011/014; SC-002/003).
- [ ] T004 Escrever em `tests/test_entrega.py` testes de timeout, status HTTP/JSON-RPC e diagnóstico sem bodies privados, constatar falha do suporte ausente e preparar em `scripts/verificar_entrega.py` a base de CLI e HTTP da biblioteca padrão conforme `contracts/entrega.md`, com `--agente http://localhost:7300`, `--mcp http://localhost:7301/mcp`, timeout de rede, ids novos, headers espelhados e `_meta` completo por request com `elicitation.form` como objeto nas capabilities, permitindo campos adicionais, sem importar tools; HTTPError deve permitir inspecionar erros JSON-RPC esperados, falhas retornam status não zero e diagnostics não imprimem bodies privados/token/segredo; não encerrar nem reiniciar processos do operador implicitamente (FR-005–007/011; SC-003).

**Checkpoint**: Features 001–004 aprovadas; suporte adicional preserva HTTP, separação de processos e opacidade, sem afirmar que o validador já passou.

## Phase 3: User Story 1 — Reproduzir a execução a partir de clone limpo (P1) — MVP

**Objetivo**: Permitir instalação, startup e aceitação oficial usando somente instruções públicas.
**Teste independente**: Em clone temporário da revisão candidata, com Python 3.12+ e segredo próprio, instalar os dois pacotes, executar pip check, subir processos separados nas portas 7301/7300 e obter as 36 verificações PASS com saída 0. Repetições começam com ambos reiniciados.

### Testes e implementação

- [ ] T005 [US1] Escrever em `tests/test_entrega.py` verificações unittest dos manifests instaláveis, Python >=3.12 e dependências diretas/build com versões exatas, ausência de SDK de LLM e compatibilidade dos pacotes com os entrypoints existentes; testar constraints portáveis sem entradas editáveis/paths locais e constatar falha dos casos novos de empacotamento/constraints antes de T006–T008, sem exigir falha de invariantes já satisfeitas; reaproveitar os testes de startup das features 001/003 para padrões de portas e segredo inválido (FR-001–003/012; SC-001).
- [ ] T006 [P] [US1] Conferir e ajustar `servidor-mcp/pyproject.toml` para instalação editável src, Python >=3.12 e pins mcp==2.3.0, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0, preservando backend de build com versão exata e entrypoint `python -m ponte_mcp`, sem extras fora de escopo; manter a versão exata validada nos dois manifests antes de T008, sem exigir troca de pin pelo anúncio de capabilities adicionais (FR-001/002/014; SC-001).
- [ ] T007 [P] [US1] Conferir e ajustar `agente/pyproject.toml` para instalação editável src, Python >=3.12 e pins mcp==2.3.0, a2a-sdk[http-server]==1.2.3, starlette==0.48.0, uvicorn==0.31.1, sse-starlette==3.0.3 e pydantic==2.12.0, preservando backend de build com versão exata e entrypoint `python -m ponte_agente`, sem SDK de LLM; manter o pin MCP validado em T006, sem exigir troca pelo anúncio de capabilities adicionais nem substituir teste de runtime por resolução pip (FR-001/002/012; SC-001).
- [ ] T008 [US1] Gerar `constraints.txt` a partir de venv nova contendo apenas os dois pacotes e sua resolução, usando pip freeze --exclude-editable; conferir versões exatas, ausência de paths/URLs locais e entradas de distribuição editável, sem assumir que constraints também fixa o build isolado: os backends permanecem fixados em cada pyproject.toml (FR-002; SC-001).
- [ ] T009 [US1] Instalar novamente ambos os pacotes em uma segunda venv limpa com `python -m pip install -c constraints.txt -e ./servidor-mcp -e ./agente`, executar pip check e `python -m unittest discover -s tests -p 'test_entrega.py' -v`, registrar versões/resultados reais em `docs/evidencias/manual.md` e corrigir os manifests/constraints se necessário antes de continuar (FR-001/002; SC-001).
- [ ] T010 [US1] Preparar a seção **Como rodar** de `README.md` com pré-requisitos Python 3.12+ para serviços e 3.10+ para validador, clone/cd/venv/instalação, startup em dois terminais e um worker, MCP_HOST/MCP_PORT/AGENTE_HOST/AGENTE_PORT/MCP_URL/A2A_BASE_URL e padrões do contrato; incluir geração/exportação de REQUEST_STATE_SECRET com `python3 -c "import secrets; print(secrets.token_hex(32))"`, sem valor utilizado, mesma chave no restart MCP, stderr visível e reinício de ambos antes de cada rodada oficial; manter a seção de resultados sem alegação de PASS até execução real (FR-001–004/008; SC-001/004).
- [ ] T011 [US1] Reproduzir a seção **Como rodar** de `README.md` em clone local temporário de uma revisão candidata versionada, fora da árvore e sem venv/arquivos privados copiados; gerar segredo próprio, confirmar endpoints 7301/mcp, 7300/a2a e card well-known, e registrar revisão, ambiente, comandos e desvios em `docs/evidencias/manual.md`; corrigir instruções e repetir somente o que foi afetado (FR-001–003/011; SC-001).
- [ ] T012 [US1] Com ambos os processos do clone recém-iniciados, executar `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`, salvar stdout/stderr integral sem filtros em `docs/evidencias/validador.txt` e registrar status original, revisão e trace-id em `docs/evidencias/manual.md`; exigir 36 PASS, zero FAIL e status 0, preservar stderr em log externo da rodada e correlacionar o trace-id impresso pelo validador com os requests do agente, distinguindo-os do cliente direto; não mascarar status por cat/tee nem reutilizar reservas consumidas (FR-004/005/010; SC-001/002).

**Checkpoint**: MVP reproduzível e primeira aceitação oficial real; ainda faltam auditoria manual e fechamento documental para declarar a entrega completa.

## Phase 4: User Story 2 — Auditar a ponte e as proteções exigidas (P1)

**Objetivo**: Demonstrar proteções e rastreamento não comprovados apenas pelos 36 testes oficiais.
**Teste independente**: Executar os cenários desta fase em bases próprias, incluindo restart somente do MCP com a mesma chave; verificar resultados por HTTP e registrar evidências sanitizadas. A execução oficial anterior não é pré-condição lógica, mas não se reutiliza seu estado de reservas.

### Testes e implementação do verificador

- [ ] T013 [US2] Acrescentar em `tests/test_entrega.py` testes do suporte adicional: CLI/URLs inválidas e timeout falham, HTTPError preserva código esperado, arquivos temporários incompletos são recusados, emissão/retomada não imprimem token e evidência de trace sem descoberta ou com retry de id igual é rejeitada; usar unittest.mock só para o suporte, sem apresentar esses mocks como prova de restart/HTTP real; executar falhas iniciais dos casos novos antes de T014–T016 (FR-005–007; SC-003).
- [ ] T014 [US2] Implementar `--caso reinicio-mcp --fase emitir|retomar --estado CAMINHO_TEMP` em `scripts/verificar_entrega.py`: emitir conflito inicial sala-garagem em 2026-11-03 14h–15h (-03:00), descobrir tools antes da chamada, guardar pedido, chave, id, instante e alternativa oferecida no arquivo externo, além do token opaco sem abri-lo; respeitar literalmente "O segredo permanece no ambiente do servidor, não nesse arquivo" e "Descartar o arquivo após o cenário; não incorporá-lo às evidências públicas"; retomar com id novo, mesmos argumentos, chave e requestState dentro de params, confirmando reserva e consulta posterior antes de 600s sem imprimir o estado (FR-005/006; SC-003).
- [ ] T015 [US2] Implementar `--caso rastreamento --log-mcp CAMINHO_LOG` em `scripts/verificar_entrega.py` para iniciar pedido A2A de conflito com trace-id exclusivo, continuar com alternativa válida e correlacionar somente esse cenário no stderr MCP; exigir tools/list antes da primeira tools/call do agente, resources/read da política, método/id/traceparent nos requests observados, trace-id estável e ids distintos no par inicial/retry; não aceitar descoberta do cliente direto do validador como prova de descoberta do agente (FR-005; SC-003).
- [ ] T016 [US2] Implementar `--caso privacidade` em `scripts/verificar_entrega.py` com reserva direta, pausa exata, escolha inválida mantendo lista/identidade, aceite, recusa real via MCP, falha de domínio com mensagem exata, GetTask e rejeição de SendMessage nos três estados terminais; manter duas Tasks pausadas em intervalos distintos para evitar interferência, retomá-las em ordem invertida e conferir responsáveis/salas/intervalos próprios; varrer card, status, history, artifacts e erros por chaves/estruturas privadas, sem abrir requestState nem calcular alternativas no agente (FR-007; SC-003).

### Execução e evidências reais

- [ ] T017 [US2] Executar os testes do suporte em `tests/test_entrega.py` e a regressão HTTP/subprocesso de `servidor-mcp/tests/test_mrtr.py`; registrar em `docs/evidencias/manual.md` casos de estado adulterado/expirado com -32602, argumentos divergentes rejeitados ou executados apenas com os valores selados, sem efeito dos valores adulterados, e capability form ausente/genérica/url-only com -32021, HTTP 400 e requiredCapabilities; demonstrar expiração pelo teste de relógio controlado no servidor isolado, sem reduzir TTL 600 de produção, fabricar token no agente ou chamar uma simulação do transporte de prova HTTP (FR-006; SC-003).
- [ ] T018 [US2] Executar as fases emitir/retomar de `scripts/verificar_entrega.py` em base própria, reiniciando manualmente somente o MCP entre elas com mesma chave, nome/audience ponte-salas e antes de 600s; registrar em `docs/evidencias/manual.md` que o processo mudou, os ids diferem e a reserva foi confirmada por HTTP sem memória de continuação, descartando o arquivo temporário mesmo em falha (FR-005/006; SC-003).
- [ ] T019 [US2] Reiniciar ambos os processos e reservar um log externo exclusivo antes de executar o caso rastreamento de `scripts/verificar_entrega.py`; registrar em `docs/evidencias/manual.md` somente trechos sanitizados com tools/list, resources/read, tools/call inicial e retry, método/id/traceparent e trace-id A2A comum, sem publicar bodies MCP nem token (FR-005; SC-003).
- [ ] T020 [US2] Reiniciar ambos para base própria e executar o caso privacidade de `scripts/verificar_entrega.py`, registrando em `docs/evidencias/manual.md` os resultados de cada fluxo, texto `alternativas: sala-fusca, sala-mirante` no conflito inicial limpo, artifact reserva e politica igual à primeira linha do resource, isolamento e terminalidade; uma escolha inválida não deve chamar novamente o MCP ou criar reserva (FR-007; SC-003).
- [ ] T021 [US2] Executar a regressão de `agente/tests/test_ponte.py` e `agente/tests/test_agente_direto.py` para complementar a varredura pública com tokens sentinela conhecidos: exigir igualdade literal no eco, mesma chave/inputResponses, novo id no retry, opacidade sem decodificação e ausência dos valores completos em toda serialização A2A; registrar em `docs/evidencias/manual.md` o alcance distinto das provas unitárias e HTTP, sem publicar tokens reais (FR-005/007; SC-003).
- [ ] T022 [US2] Executar os casos de determinismo das features 001/004 partindo do mesmo estado inicial em processos separados e registrar em `docs/evidencias/manual.md` a comparação do resultado de domínio, ordem das alternativas e estados, permitindo identidades únicas; comprovar também que reserva criada afeta consulta posterior do mesmo processo, sem exigir mesmo resultado após mutação da base (FR-011/012; SC-003/005; constituição IV).
- [ ] T023 [US2] Completar a matriz de evidências em `docs/evidencias/manual.md` para todos os cenários de FR-005–007 e AC-001–AC-037, distinguindo suíte original, testes isolados e observação manual; para lacunas ou falhas registrar FR da capacidade responsável, corrigir e repetir a validação afetada antes de aprovar o gate, sem dispensar critério por limitação de SDK (FR-004–007/013; SC-002/003).

**Checkpoint**: 100% dos cenários manuais têm comando e resultado verificável, com proteção/opacidade, trace, restart e terminalidade demonstrados; mocks de suporte não substituem provas dos protocolos.

## Phase 5: User Story 3 — Entregar documentação fiel e repositório íntegro (P2)

**Objetivo**: Fechar README/evidências de uma revisão identificada e preparar o fork público na main.
**Teste independente**: Revisar as quatro seções contra código e evidências, comparar arquivos protegidos ao starter e reproduzir comandos em clone limpo da candidata final; verificar posteriormente o mesmo conteúdo na main pública.

- [ ] T024 [US3] Redigir **Onde a ponte acontece** em `README.md` apontando os símbolos e caminhos reais de `agente/src/ponte_agente/ponte.py`, `agente/src/ponte_agente/mcp_host.py`, `agente/src/ponte_agente/tasks.py` e `agente/src/ponte_agente/handler.py`: input_required → pausa, continuação privada por Task, envio original com novo id, inputResponses e eco opaco; conferir os símbolos na implementação, sem publicar estado nem duplicar política (FR-008; SC-004).
- [ ] T025 [US3] Redigir **Decisões técnicas** em `README.md` com a stack instalada, pins/constraints e escolhas reais de `servidor-mcp/src/ponte_mcp/app.py` e `servidor-mcp/src/ponte_mcp/mrtr.py`: AES-256-GCM oficial, TTL 600s, REQUEST_STATE_SECRET hex de pelo menos 32 bytes aleatórios, audience estável e retomada sem memória MCP; explicar Tasks/reservas em memória e seus limites de restart sem prometer persistência (FR-002/003/009; SC-004).
- [ ] T026 [US3] Documentar em **Decisões técnicas** de `README.md` as diferenças de SDK efetivamente observadas e seus impactos com trechos sanitizados de teste/log e fonte oficial de versão identificada, incluindo anúncio form+url, recebimento raw de input_required, perfil A2A sem header de versão e GetTask como Task direta quando aplicáveis; anúncio form+url é permitido e FR-008 deve ser comprovado pela presença de form em cada request; não alterar SDK/protocolo nem declarar atendido requisito ausente por ressalva (FR-013/014; SC-003/004).
- [ ] T027 [US3] Fixar a candidata funcional final, executar regressões afetadas por correções e cenários manuais pendentes, reiniciar ambos e repetir o comando oficial integral salvando `docs/evidencias/validador.txt`; atualizar em `docs/evidencias/manual.md` revisão/estado exato, ambiente, status e pendências, exigindo novamente 36 PASS/zero FAIL/status 0; qualquer mudança posterior em código, manifests ou constraints invalida evidências afetadas e exige nova rodada oficial em base limpa (FR-004/006/007/010; SC-002/003).
- [ ] T028 [US3] Substituir em `README.md` o enunciado pelas quatro seções exigidas e preencher **Saída do validador** com cópia integral real, byte a byte dentro de bloco de código, de `docs/evidencias/validador.txt` produzido em T027; vincular a revisão/estado testado e as evidências manuais sem recortar linhas ou inventar resultados; mudanças apenas documentais que transcrevem evidência não alteram a revisão funcional testada (FR-008/010; SC-004).
- [ ] T029 [US3] Comparar `dados/`, `validador/` e `exemplos/` com o commit original do starter registrado em T001 e também verificar alterações staged/unstaged/untracked nesses diretórios; conferir estrutura e dois processos HTTP, registrar referência/comandos/resultado em `docs/evidencias/manual.md` e bloquear a entrega se houver divergência, sem restaurar arquivos automaticamente (FR-011; SC-005).
- [ ] T030 [US3] Seguir apenas o `README.md` final em novo clone temporário da candidata versionada, com venv limpa e segredo independente, executar pip check, startup e comando oficial em base limpa; guardar a última saída real em `docs/evidencias/validador.txt`, sincronizá-la com a seção do README e registrar reprodução/status em `docs/evidencias/manual.md`; repetir gates afetados se a reprodução exigir correção de código/configuração (FR-001–004/008/010; SC-001/002/004).
- [ ] T031 [US3] Conferir o remoto e a identidade de um único fork público de devfullcycle/desafio-a2a-com-mcp, a branch de destino main e o link final a registrar em `docs/evidencias/manual.md`; diferenciar branch de trabalho dev da main de entrega e verificar que nenhum arquivo requerido depende de caminho privado, serviço hospedado ou segundo repositório; preparar a revisão final sem publicar antes dos gates seguintes (FR-012; SC-005).
- [ ] T032 [US3] Revisar `README.md` e `docs/evidencias/manual.md` contra a candidata reproduzida: quatro seções, referências de código existentes, comandos/versões reais, saída integral mais recente e ausência de promessas de persistência; garantir que os 37 AC possuem evidência ou pendência bloqueante e que nenhuma ressalva foi contada como sucesso (FR-008–013; SC-003–005).

**Checkpoint**: Documentação reproduzida e coerente com a candidata funcional, arquivos protegidos íntegros e destino público de entrega identificado.

## Phase 6: Polish — gates transversais e entrega

- [ ] T033 Consolidar em `docs/evidencias/manual.md` a revisão dos cinco princípios, FR-001–014/SC-001–005 e AC-001–AC-037, incluindo exclusões constitucionais completas e distinção entre dependências transitivas e recursos ativados; conferir ausência de LLM/ORM/banco/auth/OAuth/streaming A2A/SSE de produto/push/GUI/containers/deploy/persistência de reservas/telemetria adicional, preservando Streamable HTTP; manter gate reprovado se faltar evidência obrigatória (FR-011–014; SC-003/005).
- [ ] T034 Auditar os arquivos versionáveis e o histórico que será publicado, inclusive `README.md`, `docs/evidencias/manual.md`, `docs/evidencias/validador.txt`, `constraints.txt` e `.gitignore`, para impedir publicação de REQUEST_STATE_SECRET utilizado, arquivos temporários, tokens reais gerados nesta execução ou paths privados, distinguindo fixtures públicas originais que permanecem protegidas; conferir igualdade da saída do README com o arquivo e validade dos links locais; se encontrar vazamento, bloquear publicação e registrar/corrigir sem reescrever histórico ou ocultar o problema automaticamente (FR-003/008/010/012; SC-004/005).
- [ ] T035 Consolidar e publicar a revisão aprovada na main do único fork público identificado em T031, incluindo `README.md`, `constraints.txt`, `scripts/verificar_entrega.py`, `tests/test_entrega.py` e `docs/evidencias/`, somente após T029–T034 aprovadas; não usar force-push nem remover trabalho alheio e reabrir os gates se houver mudança funcional durante a integração à main (FR-012; SC-005).
- [ ] T036 Conferir na main pública os artefatos da revisão entregue, o vínculo de fork e o estado inalterado de `dados/`, `validador/` e `exemplos/`; entregar o hash publicado e o link único já documentado em `docs/evidencias/manual.md`, apenas conferindo os arquivos sem criar edição local após o push; não tratar branch local, evidência antiga ou publicação parcial como conclusão (FR-010–012; SC-004/005).

## Dependências e ordem de execução

```text
Features 001 → 002 → 003 → 004 implementadas e verificadas
  → Setup T001 → T002
  → Fundação T003 → T004
  → US1 T005 → {T006, T007} → T008 → T009 → T010 → T011 → T012
  → US2 T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020 → T021 → T022 → T023
  → US3 T024 → T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032
  → Polish T033 → T034 → T035 → T036
```

- US1 e US2 dependem logicamente apenas da fundação; a ordem sequencial sugerida evita disputa pelos serviços e pelo mesmo arquivo de evidências. US3 consolida as duas e depende de seus resultados.
- T006/T007 aguardam os testes de T005; são o único grupo `[P]`, com manifests diferentes. T008 aguarda ambos e nenhum processo deve usar um ambiente enquanto ele é reinstalado.
- T013 testa suporte novo já esboçado na fundação; T014–T016 compartilham o script e permanecem sequenciais. Cada execução T018–T020 usa sua própria base e log; não executar cenários mutantes simultaneamente nas mesmas portas.
- T015/T019 pressupõem agente recém-iniciado para observar sua descoberta. Cada cenário de duas Tasks mantém pausas simultâneas de forma intercalada; não exige concorrência de escrita no mesmo milissegundo.
- T027 gera a evidência oficial da candidata; T030 é a reprodução final e passa a ser a última execução registrada. T028/T030 sincronizam o README após a captura, preservando logs/status completos e a identidade da revisão funcional. Mudança funcional posterior exige voltar a T027/T030; edição documental de transcrição exige revisão, sem fabricar nova execução.
- A comparação de T029 usa a base externa original, além do diff local. T035 aguarda clone limpo, integridade, escopo e auditoria de segredos; a publicação é trabalho futuro da implementação, não desta geração de tarefas.

## Exemplos de paralelismo por história

### US1

Após T005, executar T006 em `servidor-mcp/pyproject.toml` e T007 em `agente/pyproject.toml` em paralelo. Aguardar ambos antes de gerar constraints ou instalar. As execuções nas portas padrão são sequenciais.

### US2

Não há paralelismo seguro entre as tarefas atuais: T014–T016 editam o mesmo script, T017–T023 atualizam `docs/evidencias/manual.md` e os cenários escrevem reservas. Executar em sequência; duas Tasks pausadas são parte do teste de isolamento, não autorização para compartilhar uma base entre testes independentes.

### US3

Não há paralelismo seguro: as tarefas convergem em `README.md` e nas mesmas evidências; T027/T030 precisam de execução isolada e T028 depende da saída real. A publicação aguarda todos os gates. Não aplicar `[P]` apenas porque os títulos das seções diferem.

## Estratégia de implementação

1. Concluir setup e fundação, resolvendo pendências nas capacidades de origem antes de trabalhar na entrega.
2. Entregar US1 como MVP: instalação reproduzível e 36 PASS reais. Esse checkpoint não dispensa os critérios manuais nem constitui a entrega final.
3. Concluir US2 em bases controladas: provas HTTP, restart real, rastreabilidade, integridade/expiração, privacidade e isolamento, reaproveitando testes das features anteriores.
4. Concluir US3 com pontos reais da ponte, decisões efetivas e evidências fiéis. Reproduzir o README final em clone limpo, sincronizar a última saída e revisar os arquivos protegidos.
5. Fechar gates de escopo/segredos, integrar e publicar na main, verificar os artefatos públicos e entregar o link. Não introduzir CI, infraestrutura ou comportamento de produto novo.

## Cobertura para análise

| Requisito / critério | Tarefas |
| --- | --- |
| FR-001 | T005, T009, T010, T011, T012, T030 |
| FR-002 | T005, T006, T007, T008, T009, T010, T025 |
| FR-003 | T002, T005, T010, T011, T025, T034 |
| FR-004 | T001, T003, T010, T012, T023, T027, T030 |
| FR-005 | T001, T003, T004, T012, T013, T014, T015, T018, T019, T021, T023 |
| FR-006 | T001, T003, T004, T013, T014, T017, T018, T023, T027 |
| FR-007 | T001, T003, T004, T013, T016, T020, T021, T023, T027 |
| FR-008 | T010, T024, T028, T030, T032, T034 |
| FR-009 | T025, T032 |
| FR-010 | T012, T027, T028, T030, T032, T034, T036 |
| FR-011 | T001, T003, T004, T011, T022, T029, T033, T036 |
| FR-012 | T002, T005, T007, T022, T031, T033, T034, T035, T036 |
| FR-013 | T023, T026, T032, T033 |
| FR-014 | T003, T006, T026, T033 |
| SC-001 | T005–T012, T030 |
| SC-002 | T001, T003, T012, T023, T027, T030 |
| SC-003 | T001, T003, T004, T013–T023, T026, T027, T032, T033 |
| SC-004 | T002, T010, T024–T026, T028, T030, T032, T034, T036 |
| SC-005 | T001, T022, T029, T031–T036 |

**Contagem**: 36 tarefas — setup 2; fundação 2; US1 8; US2 11; US3 9; acabamento 4. Duas tarefas `[P]` em um grupo. Cobertura planejada: 14 FR e 5 SC; não é declaração de aprovação dos testes ou da entrega.
