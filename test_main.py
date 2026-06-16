"""
Tests de regresión de la lógica de parseo y mapeo (sin OCR ni Tesseract).

Ejecutar:  py -3.14 -m unittest -v
Cubre las funciones puras: normalización, extracción de metadatos/tablas,
clasificación de operaciones (exacta/difusa/desconocida) y validaciones.
"""

import unittest

import main


class TestNormalizacion(unittest.TestCase):
    def test_normalizar_operacion_mayusculas_sin_tildes(self):
        self.assertEqual(main.normalizar_operacion("  Eliminación  Noticia "),
                         "ELIMINACION NOTICIA")

    def test_normalizar_asunto(self):
        self.assertEqual(main.normalizar_asunto("borrado   completo"), "BORRADO COMPLETO")


class TestMetadata(unittest.TestCase):
    def test_radicado_y_fecha(self):
        texto = ("Radicado N* 2026107017030203/MDN-COGFM-COEJC-DADAE\n"
                 "Bogotá D.C, 29 de mayo de 2026")
        radicado, fecha = main.extraer_metadata(texto)
        self.assertTrue(radicado.startswith("2026107017030203"))
        self.assertEqual(fecha, "29 DE MAYO DE 2026")

    def test_fecha_respaldo_sin_bogota(self):
        _, fecha = main.extraer_metadata("documento del 5 de enero de 2025 sin ciudad")
        self.assertEqual(fecha, "5 DE ENERO DE 2025")

    def test_sin_metadata(self):
        radicado, fecha = main.extraer_metadata("texto cualquiera sin datos")
        self.assertIsNone(radicado)
        self.assertIsNone(fecha)


class TestExtraerTablas(unittest.TestCase):
    def _tablas(self, texto):
        return main.extraer_tablas(main.limpiar_texto(texto))

    def test_tabla_simple(self):
        texto = ("SOLICITUD MÓDULO 1862 Borrado Completo\n"
                 "123 | 456 | 789\nTOTAL 3 REGISTROS")
        tablas = self._tablas(texto)
        self.assertEqual(len(tablas), 1)
        self.assertEqual(tablas[0]["modulo"], 1862)
        self.assertEqual(tablas[0]["ids"], [123, 456, 789])
        self.assertEqual(tablas[0]["total"], 3)

    def test_tolera_modulo_con_cero_y_registr0s(self):
        # OCR que confunde O por 0
        texto = ("SOLICITUD M0DUL0 1476 Eliminar SIDAE\n"
                 "100 | 200\nTOTAL 2 REGISTR0S")
        tablas = self._tablas(texto)
        self.assertEqual(len(tablas), 1)
        self.assertEqual(tablas[0]["modulo"], 1476)


class TestClasificarOperacion(unittest.TestCase):
    def test_exacta(self):
        self.assertEqual(main.clasificar_operacion(1862, "Borrado Completo"), (643, True))

    def test_difusa_falta_palabra(self):
        # 'BORRADO DOCUMENTOS' debe casar con 'BORRADO DE DOCUMENTOS' -> 650
        sub, reconocida = main.clasificar_operacion(1862, "Borrado Documentos")
        self.assertEqual(sub, 650)
        self.assertTrue(reconocida)

    def test_difusa_ruido_ocr(self):
        sub, reconocida = main.clasificar_operacion(1862, "BORRADO COMPLET0")
        self.assertEqual(sub, 643)
        self.assertTrue(reconocida)

    def test_desconocida_va_a_fallback(self):
        sub, reconocida = main.clasificar_operacion(1476, "Eliminar SIDAE")
        self.assertEqual(sub, main.SUBTEMA_FALLBACK)
        self.assertFalse(reconocida)


class TestDataFrame(unittest.TestCase):
    def test_generar_dataframe_cuenta_filas(self):
        tablas = [
            {"modulo": 1862, "operacion": "Borrado Completo", "ids": [101, 102, 103], "total": 3},
            {"modulo": 1476, "operacion": "Borrado Completo", "ids": [201, 202], "total": 2},
        ]
        df = main.generar_dataframe(tablas)
        self.assertEqual(len(df), 5)
        self.assertEqual(df.iloc[0]["TEMA_SOPORTE_FK"], 383)   # 1862
        self.assertEqual(df.iloc[3]["TEMA_SOPORTE_FK"], 385)   # 1476


class TestAdvertencias(unittest.TestCase):
    def test_descuadre_y_operacion_desconocida(self):
        tablas = [{"modulo": 1476, "operacion": "Eliminar SIDAE", "ids": [1, 2], "total": 5}]
        adv = main._generar_advertencias(tablas, "RAD-1", "1 DE ENERO DE 2025")
        # Debe avisar del descuadre (2 vs 5) y de la operación no reconocida.
        self.assertTrue(any("5 registros" in a or "5 registro" in a for a in adv))
        self.assertTrue(any("no reconocida" in a for a in adv))


if __name__ == "__main__":
    unittest.main(verbosity=2)
