# Evidências manuais — conformidade da entrega

Baseline do starter: commit `263f17e202fd861d14aa7a5e6a539d13a62857c3` (`initial commit`).
Revisão funcional dos serviços MCP e A2A exercitada abaixo: `b4e5e23fcc8f80b744cb97885c5bc121e1110ebc`.
Os arquivos de entrega (`constraints.txt`, `scripts/verificar_entrega.py`, `tests/test_entrega.py`, `README.md` e `docs/evidencias/`) fazem parte do working tree dessa execução.
Python 3.12.12. Versões diretas instaladas: mcp 2.3.0, a2a-sdk 1.2.3, starlette 0.48.0, uvicorn 0.31.1, sse-starlette 3.0.3, pydantic 2.12.0. Build pin: hatchling 1.27.0, instalado só no ambiente isolado de build.

Fork público único: https://github.com/fabiocsm/desafio-a2a-com-mcp, fork de `devfullcycle/desafio-a2a-com-mcp`, branch de trabalho `dev`, branch de entrega prevista `main`. A publicação na `main` permanece pendente até um push explícito. Nenhum arquivo exigido depende de caminho privado, serviço hospedado ou segundo repositório.

## Inventário AC-001–AC-037

| AC | Spec / FR de origem | Prova | Resultado |
| --- | --- | --- | --- |
| AC-001 | 001 FR-001, FR-002 | validador 01; `test_mcp_http` descoberta | passou |
| AC-002 | 001 FR-003 | validador 02 | passou |
| AC-003 | 001 FR-004 | validador 03 | passou |
| AC-004 | 001 FR-012 | validador 04 e 05 | passou |
| AC-005 | 001 FR-011 | validador 06 | passou |
| AC-006 | 001 FR-010 | validador 07 e 08 | passou |
| AC-007 | 001 FR-006, FR-009 | validador 09–12 | passou |
| AC-008 | 001 FR-014 | stderr MCP com `method`, `id` e `traceparent` | passou |
| AC-009 | 002 FR-002, FR-003 | validador 13; `test_mrtr` | passou |
| AC-010 | 002 FR-001, FR-003 | validador 14; privacidade `alternativas: sala-fusca, sala-mirante` | passou |
| AC-011 | 002 FR-005 | validador 15; `test_matriz_capabilities_por_request_..._t021` | passou |
| AC-012 | 002 FR-009, FR-012 | validador 16 | passou |
| AC-013 | 002 FR-010 | validador 17; matriz `-32602` em `test_mrtr` | passou |
| AC-014 | 002 FR-011 | validador 18 | passou |
| AC-015 | 002 FR-008 | `scripts/verificar_entrega.py --caso reinicio-mcp` após restart só do MCP | passou |
| AC-016 | 002 FR-007 | `ler_segredo_estado` rejeita segredo curto; nenhum segredo no código | passou |
| AC-017 | 002 FR-013 | validador 19; privacidade `escolha=recusar` | passou |
| AC-018 | 003 FR-006 | log do rastreamento: `tools/list` `ponte-*` antes do primeiro `tools/call` do agente | passou |
| AC-019 | 003 FR-010 | trace-id `51e18768e7e2c27340e99282e3a4e142` nos requests `ponte-*` | passou |
| AC-020 | 003 FR-008 | `test_gate_fr008_declara_form_em_cada_request_com_capabilities_adicionais` | passou |
| AC-021 | 003 FR-002 | validador 21 | passou |
| AC-022 | 003 FR-002 | validador 22 e 23 | passou |
| AC-023 | 003 FR-004, FR-011 | validador 24; privacidade reserva direta | passou |
| AC-024 | 003 FR-007, FR-011 | validador 25; artifact `politica` = `2026-11-01` | passou |
| AC-025 | 003 FR-013 | validador 26; GetTask nos três estados | passou |
| AC-026 | 004 FR-012 | validador 31; privacidade rejeita SendMessage terminal | passou |
| AC-027 | 003 FR-012 | validador 35; histórico `Sala inexistente: sala-delorean` | passou |
| AC-028 | 004 FR-001, FR-002 | validador 27 e 28; texto exato da pausa inicial | passou |
| AC-029 | 004 FR-007, FR-008, FR-009 | validador 30; aceite em ordem invertida | passou |
| AC-030 | 004 FR-010 | validador 32 | passou |
| AC-031 | 004 FR-006 | validador 29; `escolha=sala-porao` manteve a pausa e a sala livre | passou |
| AC-032 | 004 FR-013 | validador 33; Tasks Doc/Biff retomadas em ordem invertida | passou |
| AC-033 | 004 FR-004 | validador 34; varredura do caso privacidade sem chaves privadas | passou |
| AC-034 | 005 FR-004 | 36 PASS, 0 FAIL, status 0 | passou |
| AC-035 | 005 FR-011 | `git diff 263f17e -- dados validador exemplos` sem diferença | passou |
| AC-036 | 003 FR-005; 004 FR-014 | validador 36; `test_dois_pedidos_iguais_pausam_com_o_mesmo_texto`; sem SDK de LLM | passou |
| AC-037 | 005 FR-001, FR-008, FR-009, FR-010 | README com as quatro seções e a saída integral | passou, reprodução em clone ainda registrada abaixo |

## Inventário FR-001–FR-014 e SC-001–SC-005 da spec 005

| Item | Resultado |
| --- | --- |
| FR-001 | passou — comandos de clone, venv, constraints e portas no README; segunda venv instalou com `-c constraints.txt` |
| FR-002 | passou — pins exatos e `constraints.txt` sem path editável; `pip check` sem quebra |
| FR-003 | passou — README ensina `secrets.token_hex(32)`; o valor usado não está nos artefatos |
| FR-004 | passou — validador oficial, status 0 |
| FR-005 | passou — descoberta, trace-id e ids distintos |
| FR-006 | passou — restart real, `-32602`, argumentos, `-32021` e expiração com relógio controlado |
| FR-007 | passou — caso `privacidade` |
| FR-008 | passou — quatro seções e símbolos reais da ponte |
| FR-009 | passou — AES-256-GCM, TTL 600 e Tasks em memória |
| FR-010 | passou — bloco do README igual a `docs/evidencias/validador.txt` |
| FR-011 | passou — protegidos iguais ao starter; dois processos HTTP |
| FR-012 | passou no inventário do fork e na ausência de LLM; publicação na `main` ainda pendente |
| FR-013 | passou — diferenças de SDK descritas com fonte e teste |
| FR-014 | passou — escopo preservado; dependências transitivas não habilitam streaming nem telemetria de produto |
| SC-001 | passou na venv limpa com constraints |
| SC-002 | passou — 36/36 |
| SC-003 | passou — provas HTTP e suítes isoladas distintas |
| SC-004 | passou — README fiel à execução `51e18768e7e2c27340e99282e3a4e142` |
| SC-005 | parcial — fork identificado e protegidos íntegros; a `main` pública ainda não recebeu este commit |

## Suítes 001–004

- Revisão/estado de código testado, versão Python e versões diretas instaladas: `b4e5e23`, Python 3.12.12, pins acima, venv `.venv` com instalação editável.
- Pré-condições, processos reiniciados e intervalo/sala usados: as suítes sobem subprocessos próprios e base inicial; não usam as portas 7300/7301 ocupadas.
- Comando ou cenário de teste e resultado observado: em `servidor-mcp/tests`, `python -m unittest test_salas.py test_mcp_http.py test_mrtr.py` — 38 testes, OK. Em `agente/tests`, `python -m unittest test_agente_direto.py test_mcp_host.py test_tasks.py test_ponte.py` — 40 testes, OK. O gate `test_gate_fr008_declara_form_em_cada_request_com_capabilities_adicionais` passou com `elicitation.form` objeto e capability `url` adicional permitida.
- Critério de aceite e FR da spec de origem: AC-001–AC-033 e FR-004–FR-007/FR-014 da 005, pelas specs 001–004.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou.

## Empacotamento

- Revisão/estado de código testado, versão Python e versões diretas instaladas: working tree desta execução, Python 3.12.12.
- Pré-condições, processos reiniciados e intervalo/sala usados: duas venvs novas em `/tmp`, sem processos de serviço.
- Comando ou cenário de teste e resultado observado: `pip freeze --exclude-editable` da primeira venv gerou `constraints.txt` (48 pinagens, sem `ponte-mcp`, `ponte-agente`, `file://` ou hatchling). A segunda venv executou `python -m pip install -c constraints.txt -e ./servidor-mcp -e ./agente`, `pip check` sem requisitos quebrados, freeze idêntico e `python -m unittest discover -s tests -p test_entrega.py` — 16 testes, OK.
- Critério de aceite e FR da spec de origem: FR-001, FR-002, FR-012; SC-001.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou. Os manifests já continham os pins; os testes novos de constraints falharam antes da geração do arquivo e passaram depois.

## Validador oficial

- Revisão/estado de código testado, versão Python e versões diretas instaladas: `b4e5e23` mais o working tree de entrega, Python 3.12.12, pins acima.
- Pré-condições, processos reiniciados e intervalo/sala usados: MCP e agente recém-iniciados em 7301/7300, base inicial de `dados/reservas.json`, `REQUEST_STATE_SECRET` de 32 bytes só no ambiente do MCP.
- Comando ou cenário de teste e resultado observado: `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`. Status original 0. Saída integral em `docs/evidencias/validador.txt`. Trace-id `51e18768e7e2c27340e99282e3a4e142`. No stderr MCP, o cliente direto do validador usa id hex de 12 caracteres (`tools/call id=12c0b4257404`) e não conta como descoberta do agente. Os requests do agente usam id `ponte-<uuid>`: `tools/list` `ponte-ad03391d-4644-4541-9313-735e4e1cf1a0`, `resources/read` `ponte-e82db4c1-909a-4fb5-8a65-8faab1df59c6`, depois `tools/call` `ponte-49ed37d2-4f34-45ca-8a2d-70fdf845366d` e retry `ponte-020c52ad-cbd3-45eb-b9f1-820f1cdf54a1`, todos com o mesmo trace-id e span-id diferente.
- Critério de aceite e FR da spec de origem: AC-034, FR-004, FR-005, FR-010; SC-002.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou. 36 passaram, 0 falharam.

## Restart só do MCP

- Revisão/estado de código testado, versão Python e versões diretas instaladas: mesma revisão e pins.
- Pré-condições, processos reiniciados e intervalo/sala usados: ambos reiniciados; conflito `sala-garagem` `2026-11-03T14:00:00-03:00`–`2026-11-03T15:00:00-03:00`, responsável Marty. Entre emitir e retomar, só o MCP foi encerrado e iniciado de novo (pid 47215, depois 47323), com a mesma chave e audience `ponte-salas`, antes de 600 segundos. O agente permaneceu no ar, mas o caso fala direto com o MCP.
- Comando ou cenário de teste e resultado observado: `python scripts/verificar_entrega.py --caso reinicio-mcp --fase emitir --estado "$ponte_state_file"` descobriu `reservar_sala` antes do `tools/call`, gravou pedido, chave `__main__:escolha_de_sala`, id `emit-6e8f3b13`, instante e alternativa `sala-fusca`, e o token opaco de 694 caracteres. A stdout não imprimiu o token. O arquivo não contém o segredo. Depois do restart, `--fase retomar` usou id `retry-b5cbaf86`, confirmou `sala-fusca` e a consulta posterior viu a sala ocupada. O arquivo temporário foi removido, também no caminho de sucesso.
- Critério de aceite e FR da spec de origem: AC-015, FR-005, FR-006; SC-003.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou.

## Integridade, expiração, argumentos e capability

- Revisão/estado de código testado, versão Python e versões diretas instaladas: `b4e5e23`, Python 3.12.12.
- Pré-condições, processos reiniciados e intervalo/sala usados: `servidor-mcp/tests/test_mrtr.py` sobe HTTP real e, na expiração, relógio controlado no servidor isolado. TTL de produção permanece 600.
- Comando ou cenário de teste e resultado observado: a suíte de 38 testes inclui `test_matriz_negativa_integridade_argumentos_incompletos_correlacao_e_payload_t016` (`-32602` para estado adulterado ou expirado no HTTP; argumentos divergentes não criam reserva com os valores adulterados), `test_expiracao_com_relogio_controlado_mantendo_ttl_600s_t016` e `test_matriz_capabilities_por_request_..._t021` (`-32021`, HTTP 400 e `requiredCapabilities` para form ausente, genérico ou só url).
- Critério de aceite e FR da spec de origem: AC-013, AC-014, AC-011, FR-006; SC-003.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou. O relógio controlado não substitui o restart HTTP, que está no registro anterior.

## Rastreamento

- Revisão/estado de código testado, versão Python e versões diretas instaladas: mesma revisão e pins.
- Pré-condições, processos reiniciados e intervalo/sala usados: ambos reiniciados, log exclusivo `/tmp/ponte-rastreamento.stderr.log`, agente sem descoberta prévia. Pedido A2A de conflito da garagem em 2026-11-03 14:00–15:00, responsável Trace, trace-id exclusivo.
- Comando ou cenário de teste e resultado observado: `python scripts/verificar_entrega.py --caso rastreamento --log-mcp /tmp/ponte-rastreamento.stderr.log` saiu 0. Trechos do agente, mesmo trace-id `1802485fef809dd063a477cd9b7be387`: `tools/list` `ponte-ef503bd5-7602-45ae-8e81-fa22bc3e9c1a`, `resources/read` `ponte-ef93fb46-534e-46ec-ab96-1d4d20722d24`, `tools/call` `ponte-c6d04062-a4fa-4d2d-bd54-b8aa6b89b524`, retry `ponte-55a82e6f-4281-4804-aa85-f3f876ab5b1e`.
- Critério de aceite e FR da spec de origem: AC-018, AC-019, FR-005; SC-003.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou.

## Privacidade, pausa, recusa, falha e isolamento

- Revisão/estado de código testado, versão Python e versões diretas instaladas: mesma revisão e pins.
- Pré-condições, processos reiniciados e intervalo/sala usados: ambos reiniciados em base inicial. Pausa A: garagem 2026-11-03 14:00–15:00, Doc. Pausa B: fusca 2026-11-03 16:00–17:00, Biff. Direta: aquário 09:00–10:00, Lorraine. Recusa: fusca 16:00–17:00. Falha: `sala-delorean`.
- Comando ou cenário de teste e resultado observado: `python scripts/verificar_entrega.py --caso privacidade` saiu 0. A pausa inicial foi exatamente `alternativas: sala-fusca, sala-mirante`. `escolha=sala-porao` manteve id e lista; fusca seguiu livre. A retomada invertida concluiu B em `sala-garagem` / Biff / 16:00 e A em `sala-fusca` / Doc / 14:00. O artifact `politica` é `2026-11-01`, versão lida da primeira linha `versao: 2026-11-01` de `politica://uso`. A recusa terminou `TASK_STATE_CANCELED` e mirante permaneceu livre. A sala inexistente terminou `TASK_STATE_FAILED` com `Sala inexistente: sala-delorean` no histórico. GetTask refletiu COMPLETED, CANCELED e FAILED, e SendMessage nessas Tasks foi recusado. Card, status, history, artifacts e erros não expuseram `requestState`, `inputResponses` nem `inputRequests`.
- Critério de aceite e FR da spec de origem: AC-023–AC-033, FR-007; SC-003.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou. A ausência de nova chamada MCP na escolha inválida é o comportamento de `TaskStore.repeat_pause`, corroborado por `test_escolha_invalida_repete_texto_e_depois_aceita` e, neste HTTP, pela alternativa que continuou livre.

## Opacidade complementar e determinismo

- Revisão/estado de código testado, versão Python e versões diretas instaladas: `b4e5e23`, Python 3.12.12.
- Pré-condições, processos reiniciados e intervalo/sala usados: `agente/tests/test_ponte.py` e `test_agente_direto.py` usam processos e tokens sentinela próprios, distintos do HTTP público desta evidência.
- Comando ou cenário de teste e resultado observado: 40 testes do agente OK, incluindo eco literal do token, id novo no retry, opacidade sem decodificação e `test_dois_pedidos_iguais_pausam_com_o_mesmo_texto`. Em `test_salas.py`, o mesmo estado inicial devolve `sala-fusca`, `sala-mirante` para a garagem. Identidades de Task e ids JSON-RPC continuam únicos. Reserva criada no mesmo processo altera a consulta seguinte; o restart recarrega a base.
- Critério de aceite e FR da spec de origem: AC-036, FR-011, FR-012; SC-003, SC-005; constituição IV.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou. Tokens sentinela não são publicados aqui.

## Arquivos protegidos e escopo

- Revisão/estado de código testado, versão Python e versões diretas instaladas: comparação Git, sem depender da venv.
- Pré-condições, processos reiniciados e intervalo/sala usados: árvore de trabalho contra `263f17e`.
- Comando ou cenário de teste e resultado observado: `git diff --exit-code 263f17e -- dados validador exemplos` saiu 0. `git diff --exit-code -- dados validador exemplos`, `git diff --cached --exit-code -- dados validador exemplos` e `git ls-files --others --exclude-standard -- dados validador exemplos` não mostraram alteração. Dois processos HTTP permanecem separados. Não há LLM, ORM, banco, autenticação, OAuth, streaming A2A, push, interface gráfica, container, deploy, persistência de reservas nem telemetria adicional. `sse-starlette` e `opentelemetry-api` são dependências transitivas; o transporte obrigatório continua Streamable HTTP.
- Critério de aceite e FR da spec de origem: AC-035, FR-011, FR-012, FR-014; SC-005.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva: passou.

## Pendência

A conferência da `main` pública depois do push ainda não foi feita. O link do fork está identificado. Esta pendência não converte os 36 PASS nem os cenários HTTP em falha; ela bloqueia apenas declarar a publicação concluída.
