# Auditoria de conformidade — 23/10/2026

## Escopo e conclusão

Fonte dos requisitos: README da `origin/main`, commit
`263f17e202fd861d14aa7a5e6a539d13a62857c3`, constituição 1.0.1, AGENTS.md e os
11 exemplos completos de `exemplos/wire/`. Implementação auditada: `dev`, commit
`8823afe`. Esta revisão modifica somente documentação e evidências.

Os serviços atenderam aos contratos exercitados. Não foi encontrada falha funcional
que justificasse alterar o código de aplicação. Há dois pontos de entrega:

1. **Publicação pendente:** a `main` pública continua no starter, sem implementação.
   `git fetch origin main` e `git ls-remote` pelo endereço HTTPS público confirmaram
   `263f17e`. Os testes da `dev` não comprovam uma entrega na `main`. Os itens
   T035/T036 da spec 005 e SC-005 permanecem pendentes. O pedido desta auditoria
   autoriza correção e commit; nenhum push ou merge remoto foi executado.
2. **Preparação dos testes manuais:** o passo 7 do fluxo do avaliador, executado
   imediatamente após o validador, não encontra alternativas. O README agora
   orienta reiniciar o MCP nesse ponto, preservar a chave e enviar somente
   `request.body` dos exemplos. Os cenários adicionais também têm comandos e
   pré-condições explícitos.

Não se declara conformidade integral da entrega pública enquanto a `main` não
receber a implementação. A sequência literal do enunciado também precisa da
restauração de estado indicada abaixo.

## Reprodução em clone limpo

Clone local independente de `dev` em diretório temporário, sem arquivos não
versionados do checkout de origem. Venv nova, Python 3.12.12. Foram executados
os comandos de instalação do README com `-c constraints.txt` e os dois pacotes
editáveis. `pip check`: `No broken requirements found.`

Dependências diretas: mcp 2.3.0, a2a-sdk 1.2.3, starlette 0.48.0,
uvicorn 0.31.1, sse-starlette 3.0.3, pydantic 2.12.0. SDK de tipos:
mcp-types 2.3.0. O segredo foi gerado com 32 bytes aleatórios e passado apenas
no ambiente dos subprocessos MCP, sem registrar o valor.

Dois processos independentes, portas padrão 7301/7300 e reservas iniciais.
Comando oficial:

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

Resultado: **36 passaram, 0 falharam; código de saída 0**. Trace-id:
`895c54080dba05c0872abf9caddff073`. A saída completa está no README e em
`validador.txt`, com conteúdo idêntico.

## Efeito do validador sobre o fluxo manual

O validador confirma uma reserva em fusca das 14h às 15h na verificação 30 e outra
em mirante no mesmo intervalo na 33. A garagem já está ocupada na base inicial.
Executar em seguida o corpo original do exemplo 08 produziu:

```text
TASK_STATE_FAILED
Error executing tool reservar_sala: Sem alternativas disponiveis no intervalo
```

Esse resultado respeita a política e a exigência de manter reservas criadas
visíveis. Retornar novamente as duas alternativas sem restaurar a base violaria
o domínio. O starter, o validador e os exemplos foram preservados.

Com base restaurada, foram reenviados o pedido do exemplo 08 e a continuação
`escolha=sala-mirante`: pausa exata `alternativas: sala-fusca, sala-mirante`,
Task concluída, `GetTask` com a mesma identidade e artifact com mirante e
`politica: 2026-11-01`. Novo pedido seguido de `escolha=recusar`: `CANCELED`.

## Critérios adicionais de protocolo e ponte

Cada cenário iniciou com sua própria base. Foram usados os comandos existentes
de `scripts/verificar_entrega.py`, exclusivamente por HTTP:

| Cenário | Resultado |
| --- | --- |
| `--caso privacidade` | saída 0; reserva direta, pausa, escolha inválida, retomadas em ordem inversa, recusa, falha de domínio, GetTask, terminais e isolamento |
| `--caso rastreamento --log-mcp <stderr>` | saída 0; descoberta e resource anteriores à reserva, trace-id preservado e retry com id novo |
| `--caso reinicio-mcp --fase emitir/retomar --estado <temporário>` | ambas saídas 0; restart real apenas do MCP, mesma chave, novo id e reserva visível em consulta posterior |

Trecho do stderr do caso de rastreamento, mantendo o mesmo trace-id
`9aa6309ec8815180649584e01cd62d9c` em todos os requests:

```text
tools/list     ponte-b3a80667-2cfd-4274-9456-c5eeaa6c68fe
resources/read ponte-8a756d56-f1cf-401e-9db8-27563654ce11
tools/list     ponte-50897e7f-c044-4e21-be90-87f56d82125e
tools/call     ponte-7dfe2f23-af8f-4e94-bba2-65bb2edbda33
tools/list     ponte-fe405898-5a6f-4900-b73f-b59e0337b9c4
tools/call     ponte-54bb9dc1-0a63-4dd5-8e59-0c6de123897a
```

No restart real, MCP PID 57295 foi substituído por 57299; agente PID 57297
permaneceu ativo. Emissão `emit-19164bc8`, retry `retry-856b6184`, reserva em
fusca confirmada antes do TTL de 600 segundos. O arquivo temporário de estado
foi removido; tokens e segredo não fazem parte desta evidência.

## Suítes complementares e restrições

No checkout auditado, com as mesmas dependências:

```text
python -m unittest discover -s servidor-mcp/tests -v   45 testes, OK
python -m unittest discover -s agente/tests -v         40 testes, OK
python -m unittest discover -s tests -v                22 testes, OK
```

Total: **107 testes**. A cobertura inclui metadados obrigatórios por request,
headers espelhados e `-32020`, capability form e `-32021`, integridade/expiração
com `-32602`, argumentos adulterados, restart com mesma chave, recusa/cancel,
mensagens exatas de domínio, política compartilhada entre consulta e reserva,
alternativas ordenadas, estados terminais, callback defensivo, opacidade do
token e ausência de herança de trace entre Tasks. A expiração é exercitada por
relógio controlado nos testes HTTP; o TTL de produção não foi reduzido.

`git diff --exit-code origin/main -- dados validador exemplos`: saída 0.
Revisão dos manifests e fontes confirmou dois processos com comunicação HTTP,
SDKs oficiais, dependências pinadas e nenhuma implementação de LLM, ORM, banco,
autenticação, streaming A2A, push, UI, containers, persistência de reservas ou
telemetria adicional. As dependências transitivas e diferenças dos SDKs continuam
documentadas no README. O token usa o codec AEAD oficial, TTL 600 e segredo
externo; o agente armazena e ecoa o estado sem decodificá-lo.

## Pendência final

Publicar a revisão validada na `main` do fork e conferir os arquivos nessa branch
remota. Até lá, o link da `main` fornecido ao avaliador contém apenas o starter.
