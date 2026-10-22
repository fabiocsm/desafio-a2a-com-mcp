"""Testes unitários de domínio para salas, política, consulta e reserva direta."""

from __future__ import annotations

import unittest

from ponte_mcp.salas import (
    ERRO_DURACAO_MSG,
    ERRO_INTERVALO_MSG,
    ERRO_JANELA_MSG,
    ErroDominio,
    EstadoSalas,
    OFFSET_SAO_PAULO,
    erro_sala_inexistente,
)


class TestValidacaoCompartilhadaT006(unittest.TestCase):
    """Testes unitários de T006 para a validação compartilhada de sala e intervalo."""

    def setUp(self) -> None:
        self.estado = EstadoSalas.carregar()

    def test_converte_instantes_para_offset_sao_paulo_e_aceita_limites(self) -> None:
        sala, ini, fim = self.estado.validar_sala_e_intervalo(
            "sala-aquario",
            "2026-11-03T11:00:00Z",
            "2026-11-03T13:00:00+00:00",
        )
        self.assertEqual(sala.id, "sala-aquario")
        self.assertEqual(ini.utcoffset(), OFFSET_SAO_PAULO.utcoffset(None))
        self.assertEqual(fim.utcoffset(), OFFSET_SAO_PAULO.utcoffset(None))
        self.assertEqual(ini.hour, 8)
        self.assertEqual(fim.hour, 10)

        _, ini2, fim2 = self.estado.validar_sala_e_intervalo(
            "sala-aquario",
            "2026-11-03T18:00:00-03:00",
            "2026-11-03T20:00:00-03:00",
        )
        self.assertEqual(ini2.hour, 18)
        self.assertEqual(fim2.hour, 20)

    def test_aceita_datas_no_passado_sem_comparar_com_data_corrente(self) -> None:
        sala, ini, fim = self.estado.validar_sala_e_intervalo(
            "sala-porao",
            "1985-10-26T09:00:00-03:00",
            "1985-10-26T10:30:00-03:00",
        )
        self.assertEqual(sala.id, "sala-porao")
        self.assertEqual(ini.year, 1985)
        self.assertEqual(fim.year, 1985)

    def test_exige_datas_com_timezone_e_formato_valido(self) -> None:
        with self.assertRaises(ValueError) as ctx1:
            self.estado.validar_sala_e_intervalo(
                "sala-aquario",
                "2026-11-03T09:00:00",
                "2026-11-03T10:00:00-03:00",
            )
        self.assertNotIsInstance(ctx1.exception, ErroDominio)

        with self.assertRaises(ValueError) as ctx2:
            self.estado.validar_sala_e_intervalo(
                "sala-aquario",
                "data-invalida",
                "2026-11-03T10:00:00-03:00",
            )
        self.assertNotIsInstance(ctx2.exception, ErroDominio)

    def test_erros_exatos_de_dominio_isolados(self) -> None:
        with self.assertRaises(ErroDominio) as ctx_sala:
            self.estado.validar_sala_e_intervalo(
                "sala-delorean",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
            )
        self.assertEqual(str(ctx_sala.exception), erro_sala_inexistente("sala-delorean"))

        for fim_invalido in ("2026-11-03T09:00:00-03:00", "2026-11-03T08:30:00-03:00"):
            with self.assertRaises(ErroDominio) as ctx_int:
                self.estado.validar_sala_e_intervalo(
                    "sala-aquario",
                    "2026-11-03T09:00:00-03:00",
                    fim_invalido,
                )
            self.assertEqual(str(ctx_int.exception), ERRO_INTERVALO_MSG)

        for ini_j, fim_j in (
            ("2026-11-03T07:59:00-03:00", "2026-11-03T09:00:00-03:00"),
            ("2026-11-03T19:00:00-03:00", "2026-11-03T20:01:00-03:00"),
            ("2026-11-03T19:00:00-03:00", "2026-11-04T09:00:00-03:00"),
        ):
            with self.assertRaises(ErroDominio) as ctx_jan:
                self.estado.validar_sala_e_intervalo("sala-aquario", ini_j, fim_j)
            self.assertEqual(str(ctx_jan.exception), ERRO_JANELA_MSG)

        with self.assertRaises(ErroDominio) as ctx_dur:
            self.estado.validar_sala_e_intervalo(
                "sala-aquario",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T11:01:00-03:00",
            )
        self.assertEqual(str(ctx_dur.exception), ERRO_DURACAO_MSG)

    def test_precedencia_deterministica_sala_intervalo_janela_duracao(self) -> None:
        with self.assertRaises(ErroDominio) as ctx1:
            self.estado.validar_sala_e_intervalo(
                "sala-inexistente",
                "2026-11-03T21:00:00-03:00",
                "2026-11-03T07:00:00-03:00",
            )
        self.assertEqual(str(ctx1.exception), erro_sala_inexistente("sala-inexistente"))

        with self.assertRaises(ErroDominio) as ctx2:
            self.estado.validar_sala_e_intervalo(
                "sala-aquario",
                "2026-11-03T07:00:00-03:00",
                "2026-11-03T06:00:00-03:00",
            )
        self.assertEqual(str(ctx2.exception), ERRO_INTERVALO_MSG)

        with self.assertRaises(ErroDominio) as ctx3:
            self.estado.validar_sala_e_intervalo(
                "sala-aquario",
                "2026-11-03T07:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
            )
        self.assertEqual(str(ctx3.exception), ERRO_JANELA_MSG)


class TestConsultaEReservaLivreUS2(unittest.TestCase):
    """Testes unitários de US2 (T009): consulta, conflito, adjacência e reserva livre."""

    def setUp(self) -> None:
        self.estado = EstadoSalas.carregar()

    def test_consulta_sala_livre_e_ocupada_sem_mutacao(self) -> None:
        disp_livre = self.estado.consultar_disponibilidade(
            "sala-aquario",
            "2026-11-03T09:00:00-03:00",
            "2026-11-03T10:00:00-03:00",
        )
        self.assertEqual(disp_livre.sala, "sala-aquario")
        self.assertTrue(disp_livre.livre)
        self.assertEqual(disp_livre.conflitos, [])

        # Reserva inicial de Marty em sala-garagem das 14h às 15h
        disp_ocupada = self.estado.consultar_disponibilidade(
            "sala-garagem",
            "2026-11-03T14:00:00-03:00",
            "2026-11-03T15:00:00-03:00",
        )
        self.assertEqual(disp_ocupada.sala, "sala-garagem")
        self.assertFalse(disp_ocupada.livre)
        self.assertEqual(len(disp_ocupada.conflitos), 1)
        conflito = disp_ocupada.conflitos[0]
        self.assertEqual(conflito.id, "res-0001")
        self.assertEqual(conflito.inicio, "2026-11-03T14:00:00-03:00")
        self.assertEqual(conflito.fim, "2026-11-03T15:00:00-03:00")
        self.assertEqual(conflito.responsavel, "Marty")

        # Consulta repetida confirma que consultar não muta o estado
        disp_ocupada_2 = self.estado.consultar_disponibilidade(
            "sala-garagem",
            "2026-11-03T14:00:00-03:00",
            "2026-11-03T15:00:00-03:00",
        )
        self.assertEqual(len(disp_ocupada_2.conflitos), 1)

    def test_adjacencia_nao_sobrepoe_e_offset_equivalente_detecta_conflito(self) -> None:
        # Adjacente antes (13h-14h) e depois (15h-16h) da reserva de Marty (14h-15h)
        antes = self.estado.consultar_disponibilidade(
            "sala-garagem",
            "2026-11-03T13:00:00-03:00",
            "2026-11-03T14:00:00-03:00",
        )
        depois = self.estado.consultar_disponibilidade(
            "sala-garagem",
            "2026-11-03T15:00:00-03:00",
            "2026-11-03T16:00:00-03:00",
        )
        self.assertTrue(antes.livre)
        self.assertTrue(depois.livre)

        # Mesmo intervalo 14h-15h (-03:00) expresso em UTC (17h-18hZ)
        em_utc = self.estado.consultar_disponibilidade(
            "sala-garagem",
            "2026-11-03T17:00:00Z",
            "2026-11-03T18:00:00+00:00",
        )
        self.assertFalse(em_utc.livre)
        self.assertEqual(len(em_utc.conflitos), 1)
        self.assertEqual(em_utc.conflitos[0].id, "res-0001")

    def test_reserva_livre_seguida_de_consulta_e_ids_unicos_limites_e_passado(self) -> None:
        r1 = self.estado.reservar_sala_livre(
            "sala-aquario",
            "2026-11-03T09:00:00-03:00",
            "2026-11-03T10:00:00-03:00",
            "Doc",
        )
        self.assertTrue(r1.reservado)
        self.assertIsNotNone(r1.reserva)
        self.assertNotIn(r1.reserva, {"res-0001", "res-0002"})
        self.assertEqual(r1.sala, "sala-aquario")
        self.assertEqual(r1.inicio, "2026-11-03T09:00:00-03:00")
        self.assertEqual(r1.fim, "2026-11-03T10:00:00-03:00")
        self.assertEqual(r1.responsavel, "Doc")
        self.assertEqual(r1.politica, "2026-11-01")
        self.assertIsNone(r1.motivo)

        # Consulta seguinte enxerga a nova reserva
        pos_consulta = self.estado.consultar_disponibilidade(
            "sala-aquario",
            "2026-11-03T09:00:00-03:00",
            "2026-11-03T10:00:00-03:00",
        )
        self.assertFalse(pos_consulta.livre)
        self.assertEqual(len(pos_consulta.conflitos), 1)
        self.assertEqual(pos_consulta.conflitos[0].id, r1.reserva)
        self.assertEqual(pos_consulta.conflitos[0].responsavel, "Doc")

        # Segunda reserva em horário adjacente (08:00-09:00) e terceira no passado (2h exatas até 20:00)
        r2 = self.estado.reservar_sala_livre(
            "sala-aquario",
            "2026-11-03T08:00:00-03:00",
            "2026-11-03T09:00:00-03:00",
            "Marty",
        )
        r3 = self.estado.reservar_sala_livre(
            "sala-porao",
            "1955-11-05T18:00:00-03:00",
            "1955-11-05T20:00:00-03:00",
            "Emmett",
        )
        self.assertEqual(len({r1.reserva, r2.reserva, r3.reserva}), 3)


class TestCatalogoEPoliticaUS1(unittest.TestCase):
    """Testes unitários de US1 (T018): cinco salas, ids únicos e política sem perda de bytes."""

    def setUp(self) -> None:
        self.estado = EstadoSalas.carregar()

    def test_listar_salas_retorna_cinco_salas_identicas_ao_json_original(self) -> None:
        import json
        from ponte_mcp.salas import DADOS_DIR

        original = json.loads((DADOS_DIR / "salas.json").read_text(encoding="utf-8"))
        lista = self.estado.listar_salas()
        self.assertEqual(len(lista.salas), 5)
        ids = [s.id for s in lista.salas]
        self.assertEqual(len(set(ids)), 5)
        serializado = [s.model_dump() for s in lista.salas]
        self.assertEqual(serializado, original)

    def test_ler_politica_preserva_bytes_e_extrai_versao_primeira_linha(self) -> None:
        from ponte_mcp.salas import DADOS_DIR

        texto_original = (DADOS_DIR / "politica-de-uso.md").read_text(encoding="utf-8")
        self.assertEqual(self.estado.ler_politica_texto(), texto_original)
        self.assertEqual(self.estado.versao_politica(), "2026-11-01")


class TestMatrizRejeicoesUS3(unittest.TestCase):
    """Testes unitários de US3 (T024): matriz das duas operações para os quatro erros, precedência e ausência de mutação."""

    def setUp(self) -> None:
        self.estado = EstadoSalas.carregar()

    def _invocar_ambas(self, sala: str, inicio: str, fim: str) -> None:
        for operacao in (
            lambda: self.estado.consultar_disponibilidade(sala, inicio, fim),
            lambda: self.estado.reservar_sala_livre(sala, inicio, fim, "Doc"),
        ):
            operacao()

    def test_quatro_erros_nas_duas_operacoes_sem_mutacao_de_estado(self) -> None:
        casos = [
            (
                "sala-delorean",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
                erro_sala_inexistente("sala-delorean"),
            ),
            (
                "sala-aquario",
                "2026-11-03T07:00:00-03:00",
                "2026-11-03T08:00:00-03:00",
                ERRO_JANELA_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T19:30:00-03:00",
                "2026-11-03T20:30:00-03:00",
                ERRO_JANELA_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T23:00:00-03:00",
                "2026-11-04T00:30:00-03:00",
                ERRO_JANELA_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T09:00:00-03:00",
                "2026-11-03T12:00:00-03:00",
                ERRO_DURACAO_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T10:00:00-03:00",
                "2026-11-03T10:00:00-03:00",
                ERRO_INTERVALO_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T10:00:00-03:00",
                "2026-11-03T09:00:00-03:00",
                ERRO_INTERVALO_MSG,
            ),
        ]

        for sala, inicio, fim, msg_esperada in casos:
            with self.subTest(op="consultar", sala=sala, inicio=inicio, fim=fim):
                with self.assertRaises(ErroDominio) as ctx_c:
                    self.estado.consultar_disponibilidade(sala, inicio, fim)
                self.assertEqual(str(ctx_c.exception), msg_esperada)

            with self.subTest(op="reservar", sala=sala, inicio=inicio, fim=fim):
                with self.assertRaises(ErroDominio) as ctx_r:
                    self.estado.reservar_sala_livre(sala, inicio, fim, "Doc")
                self.assertEqual(str(ctx_r.exception), msg_esperada)

        # Confirmar que nenhuma reserva inválida foi gravada em sala-aquario
        disp = self.estado.consultar_disponibilidade(
            "sala-aquario",
            "2026-11-03T08:00:00-03:00",
            "2026-11-03T10:00:00-03:00",
        )
        self.assertTrue(disp.livre)
        self.assertEqual(disp.conflitos, [])

    def test_precedencia_e_formatos_invalidos_nas_duas_operacoes(self) -> None:
        # Precedência nas duas operações: sala -> intervalo -> janela -> duração
        combinacoes = [
            (
                "sala-fantasma",
                "2026-11-03T21:00:00-03:00",
                "2026-11-03T07:00:00-03:00",
                erro_sala_inexistente("sala-fantasma"),
            ),
            (
                "sala-aquario",
                "2026-11-03T07:00:00-03:00",
                "2026-11-03T06:00:00-03:00",
                ERRO_INTERVALO_MSG,
            ),
            (
                "sala-aquario",
                "2026-11-03T06:00:00-03:00",
                "2026-11-03T09:30:00-03:00",
                ERRO_JANELA_MSG,
            ),
        ]
        for sala, inicio, fim, msg in combinacoes:
            with self.assertRaises(ErroDominio) as ctx_c:
                self.estado.consultar_disponibilidade(sala, inicio, fim)
            self.assertEqual(str(ctx_c.exception), msg)

            with self.assertRaises(ErroDominio) as ctx_r:
                self.estado.reservar_sala_livre(sala, inicio, fim, "Doc")
            self.assertEqual(str(ctx_r.exception), msg)

        # Datetime sem timezone ou formato inválido não inventa mensagem de domínio
        for ini_inv, fim_inv in (
            ("2026-11-03T09:00:00", "2026-11-03T10:00:00-03:00"),
            ("2026-11-03T09:00:00-03:00", "2026-11-03T10:00:00"),
            ("invalido", "2026-11-03T10:00:00-03:00"),
        ):
            with self.assertRaises(ValueError) as ctx_fc:
                self.estado.consultar_disponibilidade("sala-aquario", ini_inv, fim_inv)
            self.assertNotIsInstance(ctx_fc.exception, ErroDominio)

            with self.assertRaises(ValueError) as ctx_fr:
                self.estado.reservar_sala_livre("sala-aquario", ini_inv, fim_inv, "Doc")
            self.assertNotIsInstance(ctx_fr.exception, ErroDominio)


if __name__ == "__main__":
    unittest.main()
