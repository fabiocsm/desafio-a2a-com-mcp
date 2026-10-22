# Quickstart: Conformidade, reprodução e documentação da entrega

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

**Gate prévio**: resolver 003/FR-008 por API pública compatível e aprovar o teste de
wire com capabilities exatamente `{"elicitation": {"form": {}}}`. Enquanto o pin
anunciar form+url, esta entrega permanece pendente; registrar a limitação não
aprova o requisito. Usar os pins exatos aprovados nas features de origem, sem
trocar por latest para contornar o gate.

## Instalação da entrega em clone limpo

Depois de implementar as cinco features e gerar constraints.txt a partir de
venv limpa, seguir os comandos planejados:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -c constraints.txt -e ./servidor-mcp -e ./agente
python -m pip check
export REQUEST_STATE_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python -m ponte_mcp 2> /tmp/ponte-mcp.stderr.log
```

No segundo terminal:

```bash
. .venv/bin/activate
python -m ponte_agente
```

Não gere outra chave ao reiniciar o MCP para o teste de continuação.

## Aceitação oficial

Com ambos recém-iniciados, no terceiro terminal:

```bash
. .venv/bin/activate
mkdir -p docs/evidencias
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301 > docs/evidencias/validador.txt 2>&1
ponte_validator_status=$?
cat docs/evidencias/validador.txt
test "$ponte_validator_status" -eq 0
```

Esperado: as 36 verificações PASS e saída 0. Registrar o status original, a revisão
funcional testada e as versões instaladas em docs/evidencias/manual.md; não
substituí-lo pelo status de cat/tee. A primeira linha informa o trace-id.
Preservar o stderr externo desta rodada antes de reiniciar serviços. Nele, localizar
esse trace-id nos requests do agente e tools/list anterior à primeira chamada do
agente; não confundir com os requests diretos do cliente MCP do validador. Registrar
somente trechos método/id/traceparent sanitizados, sem bodies ou token de continuação.
O arquivo só existe após a execução real, não como saída gerada pelo planejamento.

## Restart MCP com continuação preservada

Reiniciar ambos para uma base limpa antes deste cenário, mantendo o segredo MCP.
O script abaixo é implementado somente nesta feature:

```bash
ponte_state_file="$(mktemp)"
python scripts/verificar_entrega.py --caso reinicio-mcp --fase emitir --estado "$ponte_state_file"
```

Interromper somente o MCP no primeiro terminal e executar python -m ponte_mcp
novamente com a mesma variável e redirecionamento de stderr. Não reiniciar o agente
como condição do teste. Então executar:

```bash
python scripts/verificar_entrega.py --caso reinicio-mcp --fase retomar --estado "$ponte_state_file"
rm "$ponte_state_file"
```

Esperado: confirmação real na alternativa antes de 600s, com id novo e sem memória
de continuação no servidor. Não publicar o arquivo temporário ou seu conteúdo.

## Complementos e documentação

Os testes de integração abaixo gerenciam seus próprios processos/base. As suítes
das capacidades anteriores devem existir e estar aprovadas antes da feature 005.

```bash
python -m unittest discover -s servidor-mcp/tests -v
python -m unittest discover -s agente/tests -v
python -m unittest discover -s tests -p 'test_entrega.py' -v
```

Registrar em docs/evidencias/manual.md cada cenário, comando, revisão e resultado:

| Prova | Origem e resultado esperado |
| --- | --- |
| Adulteração/expiração | servidor-mcp/tests/test_mrtr.py: HTTP real rejeita com -32602; expiração usa relógio controlado no servidor isolado, sem alterar TTL 600 de produção. |
| Argumentos adulterados | Mesma suíte: rejeição ou uso apenas dos valores selados; nenhuma reserva usa valores adulterados. |
| Form ausente/genérico/url-only | Mesma suíte: conflito que exige elicitation gera -32021, HTTP 400 e requiredCapabilities. |
| Eco/opacidade e vazamento | agente/tests/test_ponte.py: token sentinela conhecido é ecoado sem abertura/alteração e não aparece em serializações A2A; não publicar tokens reais. |

Mocks de CLI/HTTP do verificador validam seu suporte, sem substituir as provas de
protocolo por HTTP real. Não reduzir TTL de produção para acelerar a evidência.

Para rastreamento, encerrar os dois serviços usados antes, reiniciar ambos nos
terminais originais e usar um arquivo de log externo próprio no primeiro terminal:

```bash
python -m ponte_mcp 2> /tmp/ponte-rastreamento.stderr.log
```

No segundo terminal, iniciar novamente python -m ponte_agente. Somente depois de
ambos estarem disponíveis, no terceiro terminal:

```bash
python scripts/verificar_entrega.py --caso rastreamento --log-mcp /tmp/ponte-rastreamento.stderr.log
```

Esse caso inicia um fluxo A2A de conflito com trace-id exclusivo. Esperado:
tools/list do agente antes de sua primeira tools/call, resources/read da política,
mesmo trace-id em todos os requests MCP da Task e ids diferentes na chamada/retry.
Preservar o log para registrar os trechos sanitizados; não reaproveitar um agente
cuja descoberta já ocorreu em outra rodada ou aceitar descoberta do validador.

Para privacidade, encerrar e reiniciar novamente **ambos** os serviços nos dois
terminais com base limpa e log externo distinto, sem reaproveitar as reservas do
caso de rastreamento. Executar então no terceiro terminal:

```bash
python scripts/verificar_entrega.py --caso privacidade
```

Esperado: reserva direta, pausa/lista exata, escolha inválida preservando pausa,
aceite, recusa, erro de domínio no histórico, GetTask coerente, três estados
terminais definitivos, duas Tasks pausadas isoladas e nenhuma estrutura privada
nas respostas A2A. Registrar cada subcenário, não apenas o status global do script.

Inspeção local dos arquivos protegidos:

```bash
git diff --exit-code -- dados/ validador/ exemplos/
git diff --cached --exit-code -- dados/ validador/ exemplos/
git ls-files --others --exclude-standard -- dados/ validador/ exemplos/
```

Para verificar integridade, o diff do trabalho atual deve ser complementado com
comparação contra a base original do starter; um commit local já adulterado não
pode virar baseline. Os testes de integração gerenciam seus próprios processos/base.

Depois dos testes que escrevem reservas, reiniciar os dois processos antes de
uma nova suíte oficial. Registrar cenários manuais, atualizar as quatro seções
do README com pontos reais do código e documentar AES-256-GCM, TTL600, Tasks em
memória e perfil A2A de versão ausente. Se form+url ainda aparecer, registrar
003/FR-008 como falha e interromper a aceitação final, sem afirmar conformidade.
Não afirmar que as rotas seguem a negociação normativa irrestrita sem registrar
a adaptação.

Reproduzir por último o README final em clone limpo da candidata versionada e
guardar a saída integral real/status dessa execução. Sincronizar validador.txt e
a seção Saída do validador com essa última saída; registrar a revisão funcional
e terminar os arquivos de evidência antes do push. Se código/manifests/constraints
mudarem, repetir as verificações afetadas e a suíte oficial em base limpa.
Transcrever evidência em documentação não exige inventar outra execução.

Conferir a branch main e o link do fork público na entrega final. Depois do push,
somente verificar os artefatos públicos e informar hash/link, sem deixar edição
de evidência apenas local. Este guia não executa publicação ou alteração de branch
automaticamente.
