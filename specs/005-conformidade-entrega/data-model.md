# Data Model: Conformidade, reprodução e documentação da entrega

## Artefatos de entrega

| Artefato | Conteúdo / validação |
| --- | --- |
| pyproject.toml de cada pacote | runtime, build e dependências diretas exatas |
| constraints.txt | versões resolvidas a partir de venv limpa; sem paths de pacotes editáveis |
| README final | Como rodar, Onde a ponte acontece, Decisões técnicas, Saída do validador |
| validador.txt | saída completa real da última execução oficial |
| manual.md | revisão, ambiente, cenário, resultado observado e referência aos logs/testes |
| Baseline de arquivos protegidos | referência Git original ou hashes verificados contra o starter |

## Registro de evidência

Cada evidência manual identifica:
- Revisão/estado de código testado, versão Python e versões diretas instaladas.
- Pré-condições, processos reiniciados e intervalo/sala usados.
- Comando ou cenário de teste e resultado observado.
- Critério de aceite e FR da spec de origem.
- Passou/falhou com motivo; falha continua pendência, sem marcar sucesso por ressalva.

Não incluir segredo, token de continuação, body privado integral ou paths locais
como configuração necessária ao avaliador. O trace-id e os ids JSON-RPC podem
aparecer como evidência de propagação e independência das chamadas.

## Estado temporário do cenário de restart

Arquivo temporário fora do repositório com:
pedido MCP original, chave da pergunta, token e instante da emissão.
É usado apenas entre as fases emitir/retomar do verificador; o consumidor guarda,
não abre o token. O segredo permanece no ambiente do servidor, não nesse arquivo.
Descartar o arquivo após o cenário; não incorporá-lo às evidências públicas.

## Ciclo de revisão

Implementação concluída → bateria local → base limpa → validador integral →
cenários manuais em bases próprias → documentação com resultados reais →
clone limpo reproduzido → entrega do fork na main.

Qualquer mudança no código após a execução registrada exige nova validação
aplicável antes de declarar aquela saída como a última evidência da entrega.
