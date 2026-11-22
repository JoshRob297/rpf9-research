"""Fixtures de cabecera: comprobaciones que corren sin las muestras.

Las pruebas de `tests/test_rpf9.py` y `tests/test_name_recover.py` se saltan cuando no
estan los binarios de `samples/`, que no se versionan. Estas no dependen de nada: usan
los 22 x 64 bytes publicados en `raw/cabeceras/`, asi que sirven en un clon limpio y en CI.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "raw" / "cabeceras"
BIN = FIX / "headers.bin"

MAGICS = (b"RPF9", b"9FPR")


def bloques() -> list[bytes]:
    datos = BIN.read_bytes()
    return [datos[i:i + 64] for i in range(0, len(datos), 64)]


class TestCabeceras(unittest.TestCase):
    def test_tamano_y_conteo(self):
        datos = BIN.read_bytes()
        self.assertEqual(len(datos), 1408)
        self.assertEqual(len(datos) % 64, 0)
        self.assertEqual(len(bloques()), 22)

    def test_magia_en_todas(self):
        for i, b in enumerate(bloques()):
            self.assertIn(b[:4], MAGICS, f"bloque {i} sin magia RPF9")

    def test_constantes_de_cabecera(self):
        for i, b in enumerate(bloques()):
            self.assertEqual(struct.unpack_from("<I", b, 0x18)[0], 0x47A00, f"0x18 en bloque {i}")
            self.assertEqual(struct.unpack_from("<I", b, 0x1C)[0], 0x150, f"0x1c en bloque {i}")

    def test_formula_de_la_region(self):
        for i, b in enumerate(bloques()):
            toc_end = struct.unpack_from("<I", b, 0x04)[0]
            sub = struct.unpack_from("<I", b, 0x08)[0]
            entradas = struct.unpack_from("<I", b, 0x24)[0]
            byte2c = b[0x2C]
            self.assertIn(byte2c, (1, 2), f"byte 0x2c inesperado en bloque {i}: {byte2c}")
            stride = 8 + byte2c
            esperado = ((stride * entradas + 15) // 16) * 16
            self.assertEqual(toc_end - sub, esperado, f"region distinta en bloque {i}")

    def test_selector_0x2c_reparte_15_y_7(self):
        conteo = {1: 0, 2: 0}
        for b in bloques():
            conteo[b[0x2C]] += 1
        self.assertEqual(conteo, {1: 15, 2: 7})

    def test_fixture_python_coincide_con_el_binario(self):
        sys.path.insert(0, str(FIX))
        try:
            import rpf9_headers
        finally:
            sys.path.pop(0)
        self.assertEqual(len(rpf9_headers.ORDER), 22)
        concatenado = b"".join(rpf9_headers.HEADERS[n] for n in rpf9_headers.ORDER)
        self.assertEqual(concatenado, BIN.read_bytes())

    def test_tsv_tiene_22_filas_y_formula_ok(self):
        lineas = (FIX / "headers.tsv").read_text().strip().split("\n")
        self.assertEqual(len(lineas), 23)  # cabecera + 22
        for linea in lineas[1:]:
            self.assertTrue(linea.endswith("\tyes"), f"fila sin formula_ok: {linea[:40]}")

    def test_hpp_declara_22_cabeceras(self):
        texto = (FIX / "rpf9_headers.hpp").read_text()
        self.assertIn("std::array<Header, 22>", texto)
        self.assertEqual(texto.count('{"'), 22)


if __name__ == "__main__":
    unittest.main()
