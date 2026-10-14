from pathlib import Path
import sys
import unittest
import math
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
from analisis_senoidal import analizar
import medidor_backend as b


class AnalisisTests(unittest.TestCase):
    def test_inductor_con_esr_y_ventana_no_entera_y_offset_y_ruido(self):
        rng = np.random.default_rng(9)
        f, L, R, rs, gain = 5000.3, .00291, 2.41, 10, 5
        phi = math.degrees(math.atan2(2 * math.pi * f * L, R))
        z = math.hypot(R, 2 * math.pi * f * L)
        t = -.00057 + np.arange(10000) * 5.3 / f / 10000
        vr, vi = 1.5, 1.5 * rs * gain / z
        ch1 = vi * np.sqrt(2) * np.sin(2 * np.pi * f * t + .41) + .03 + rng.normal(0, .003, t.size)
        ch2 = vr * np.sqrt(2) * np.sin(2 * np.pi * f * t + .41 + np.radians(phi + 180)) - .12 + rng.normal(0, .003, t.size)
        lecturas = analizar(t, ch1, ch2, 4994)
        datos = b._procesar_matematica(*lecturas, rs)
        self.assertEqual(datos['tipo'], 'INDUCTOR')
        self.assertAlmostEqual(datos['valor_num'], L, delta=L * .001)
        self.assertAlmostEqual(datos['esr_num'], R, delta=.05)
        self.assertAlmostEqual(lecturas[2], f, delta=.2)

    def test_rechaza_ruido_senal_distorsionada_y_ausente(self):
        t = np.arange(1000) * .005 / 1000
        angulo = 2 * np.pi * 1000 * t
        seno = np.sin(angulo)
        for mala in (np.zeros(1000), seno + .2 * np.sin(3 * angulo), np.random.default_rng(7).normal(size=1000)):
            with self.assertRaises(ValueError):
                analizar(t, mala, seno, 1000)

    def test_rechaza_capturas_cortas_no_uniformes_y_no_finitas(self):
        t = np.arange(1000) * .005 / 1000
        seno = np.sin(2 * np.pi * 1000 * t)
        malas = [(t, seno[:-1], seno), (t[:20], seno[:20], seno[:20]),
                 (t / 10, seno, seno), (t[::-1], seno, seno),
                 (t, seno * float('nan'), seno)]
        for ti, vi, vr in malas:
            with self.assertRaises(ValueError):
                analizar(ti, vi, vr, 1000)


if __name__ == '__main__':
    unittest.main()
