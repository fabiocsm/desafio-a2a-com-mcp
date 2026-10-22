# Data Model: Servidor MCP de salas e reservas diretas

## Entidades e origem

| Entidade | Campos | Origem / validação |
| --- | --- | --- |
| Sala | id: str, nome: str, capacidade: int, recursos: list[str] | dados/salas.json, cinco registros, ids únicos |
| Reserva | id: str, sala: str, inicio: datetime, fim: datetime, responsavel: str | dados/reservas.json mais criações no processo |
| Política | texto: str, versao: str, janela 08:00–20:00, máximo 2h | texto original; versão extraída da primeira linha |
| Disponibilidade | sala: str, livre: bool, conflitos: list[Conflito] | calculada sem mutação |
| Conflito | id, inicio, fim, responsavel | projeção das reservas que se sobrepõem |
| ReservaOut | reserva: str ou null, reservado: bool, sala/inicio/fim/responsavel/politica: str ou null, motivo: str ou null | contrato de saída completo |
| Entrada observada | método, id, traceparent opcional e presença de metadata | apenas escopo do request; não é sessão |

## Relações e validações

- Reserva.sala referencia uma Sala existente; não criar outra fonte de catálogo no agente.
- Converter os instantes para o offset do domínio -03:00 antes de conferir a janela.
  Exigir datas com timezone; formatos rejeitados pelo schema não ganham nova mensagem
  de domínio inventada. Nenhuma comparação com a data corrente é permitida.
- Exigir fim > inicio, duração <= 2h e intervalo dentro da janela do mesmo dia.
- Sobreposição: inicio < reserva.fim e fim > reserva.inicio para a mesma sala.
  Horários adjacentes não se sobrepõem; uma reserva atravessando a noite viola a janela.
- Consultar e reservar usam a mesma função de validação e as mesmas mensagens.
  Se várias regras forem violadas, usar precedência determinística: sala, intervalo,
  janela, duração; os testes de cada erro isolam a respectiva condição.
- Uma reserva confirmada entra na coleção em memória antes da resposta, para ficar
  visível à próxima consulta. Não é exigida transação contra escrita simultânea.

## Ciclo de vida

Startup lê os arquivos protegidos e inicializa a coleção/contador. Consulta não
muda estado. Reserva livre acrescenta um registro. Shutdown perde apenas dados
transitórios. A política e os dados originais nunca são reescritos.

A continuação de conflito não é uma entidade em memória do MCP: será projetada
como estado transportado na feature 002.
