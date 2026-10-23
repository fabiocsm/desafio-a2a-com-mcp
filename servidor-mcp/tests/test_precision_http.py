"""Regressão de precisão de reservas e conflitos no transporte MCP real."""

from __future__ import annotations

from datetime import datetime
import json
import unittest

from test_mcp_http import running_mcp_server


class TestPrecisaoSubsegundoHTTP(unittest.TestCase):
    def test_reserva_e_consulta_preservam_instantes_e_json_equivalente(self) -> None:
        inicio = "2026-11-03T09:00:00.100000-03:00"
        fim = "2026-11-03T09:00:00.900000-03:00"
        with running_mcp_server() as srv:
            resultados = {}
            for nome, extra in (
                ("reservar_sala", {"responsavel": "Doc"}),
                ("consultar_disponibilidade", {}),
            ):
                status, resposta, _ = srv.request(
                    "tools/call",
                    {"name": nome, "arguments": {
                        "sala": "sala-aquario", "inicio": inicio, "fim": fim, **extra,
                    }},
                    name=nome,
                )
                self.assertEqual(status, 200)
                resultado = resposta["result"]
                self.assertEqual(resultado["resultType"], "complete")
                self.assertFalse(resultado.get("isError", False))
                texto = " ".join(parte["text"] for parte in resultado["content"])
                self.assertEqual(json.loads(texto), resultado["structuredContent"])
                resultados[nome] = resultado["structuredContent"]

            reserva = resultados["reservar_sala"]
            consulta = resultados["consultar_disponibilidade"]
            self.assertTrue(reserva["reservado"])
            self.assertFalse(consulta["livre"])
            self.assertEqual(len(consulta["conflitos"]), 1)
            conflito = consulta["conflitos"][0]
            self.assertEqual(conflito["id"], reserva["reserva"])
            for campo, esperado in (("inicio", inicio), ("fim", fim)):
                with self.subTest(campo=campo, origem="reserva"):
                    self.assertEqual(datetime.fromisoformat(reserva[campo]), datetime.fromisoformat(esperado))
                with self.subTest(campo=campo, origem="conflito"):
                    self.assertEqual(datetime.fromisoformat(conflito[campo]), datetime.fromisoformat(esperado))
                self.assertEqual(reserva[campo], conflito[campo])

            status, resposta, _ = srv.request(
                "tools/call",
                {"name": "reservar_sala", "arguments": {
                    "sala": "sala-aquario", "inicio": fim,
                    "fim": "2026-11-03T09:00:01-03:00", "responsavel": "Marty",
                }},
                name="reservar_sala",
            )
            self.assertEqual(status, 200)
            self.assertTrue(resposta["result"]["structuredContent"]["reservado"])


if __name__ == "__main__":
    unittest.main()
