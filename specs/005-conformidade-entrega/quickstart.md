# Quickstart: Conformidade, reprodução e documentação da entrega

Guia de validação **para depois da implementação**. Os módulos, testes e scripts
citados são entregáveis planejados; não foram criados ou executados por $speckit-plan.
Execute comandos a partir da raiz do repositório, salvo indicação contrária.

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

Esperado: as 36 verificações PASS e saída 0. Registrar o status original; não
substituí-lo pelo status de cat/tee. A primeira linha informa o trace-id.
No stderr, localizar esse valor e a descoberta anterior à primeira chamada do agente.
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

```bash
python -m unittest discover -s servidor-mcp/tests -v
python -m unittest discover -s agente/tests -v
python -m unittest discover -s tests -p 'test_entrega.py' -v
python scripts/verificar_entrega.py --caso rastreamento --log-mcp /tmp/ponte-mcp.stderr.log
python scripts/verificar_entrega.py --caso privacidade
git diff --exit-code -- dados/ validador/ exemplos/
```

Para verificar integridade, o diff do trabalho atual deve ser complementado com
comparação contra a base original do starter; um commit local já adulterado não
pode virar baseline. Os testes de integração gerenciam seus próprios processos/base.

Depois dos testes que escrevem reservas, reiniciar os dois processos antes de
uma nova suíte oficial. Registrar cenários manuais, atualizar as quatro seções
do README com pontos reais do código e documentar AES-256-GCM, TTL600, Tasks em
memória, form+url e perfil A2A de versão ausente. Não afirmar que as rotas seguem
a negociação normativa irrestrita sem registrar a adaptação.

Conferir a branch main e o link do fork público na entrega final; este guia
não executa publicação ou alteração de branch automaticamente.
