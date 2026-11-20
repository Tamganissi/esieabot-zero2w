"""Tests de la logique de sécurité et de conduite (sans matériel).
Lancer : cd ~/esieabot && venv/bin/python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from safety import Securite, etat_texte, melange_arcade, pwm_minimum, rampe, zone_morte  # noqa: E402


class TestZoneMorte(unittest.TestCase):
    def test_centre_nul(self):
        for v in (0.0, 0.05, -0.12, 0.12):
            self.assertEqual(zone_morte(v, 0.12), 0.0)

    def test_progressif_et_borne(self):
        self.assertAlmostEqual(zone_morte(1.0, 0.12), 1.0)
        self.assertAlmostEqual(zone_morte(-1.0, 0.12), -1.0)
        a, b = zone_morte(0.3, 0.12), zone_morte(0.6, 0.12)
        self.assertTrue(0 < a < b < 1)


class TestMelange(unittest.TestCase):
    def test_avance_droit(self):
        self.assertEqual(melange_arcade(1.0, 0.0), (1.0, 1.0))

    def test_rotation_sur_place_gauche(self):
        g, d = melange_arcade(0.0, -1.0, 1.0)
        self.assertLess(g, 0)
        self.assertGreater(d, 0)

    def test_jamais_au_dessus_de_1(self):
        for gaz in (-1, -0.5, 0, 0.5, 1):
            for vir in (-1, -0.5, 0, 0.5, 1):
                g, d = melange_arcade(gaz, vir, 1.0)
                self.assertLessEqual(abs(g), 1.0)
                self.assertLessEqual(abs(d), 1.0)


class TestRampe(unittest.TestCase):
    def test_acceleration_limitee(self):
        self.assertAlmostEqual(rampe(0.0, 1.0, 0.05), 0.05)

    def test_freinage_immediat(self):
        self.assertEqual(rampe(0.8, 0.0, 0.05), 0.0)

    def test_inversion_passe_par_zero(self):
        self.assertEqual(rampe(0.5, -0.5, 0.05), 0.0)


class TestSecurite(unittest.TestCase):
    def test_demarre_desarme(self):
        self.assertFalse(Securite().peut_rouler())

    def test_armement_refuse_si_joystick_pousse(self):
        s = Securite()
        self.assertFalse(s.armer(joysticks_au_centre=False))
        self.assertFalse(s.peut_rouler())

    def test_armement_ok(self):
        s = Securite()
        self.assertTrue(s.armer(True))
        self.assertTrue(s.peut_rouler())

    def test_urgence_verrouillee(self):
        s = Securite()
        s.armer(True)
        s.arret_urgence()
        self.assertFalse(s.peut_rouler())
        self.assertTrue(s.urgence)
        self.assertTrue(s.armer(True))  # seul A (centré) déverrouille
        self.assertTrue(s.peut_rouler())

    def test_defaut_driver_desarme(self):
        s = Securite()
        s.armer(True)
        self.assertFalse(s.peut_rouler(defaut_driver=True))
        self.assertFalse(s.peut_rouler())  # reste désarmé après disparition du défaut


class TestPwmMinimum(unittest.TestCase):
    def test_zero_reste_zero(self):
        self.assertEqual(pwm_minimum(0.0, 0.4, 0.55), 0.0)

    def test_petite_consigne_demarre_au_minimum(self):
        self.assertAlmostEqual(pwm_minimum(0.01, 0.4, 0.55), 0.4, places=1)
        self.assertLess(pwm_minimum(-0.01, 0.4, 0.55), -0.39)

    def test_jamais_au_dessus_de_la_limite(self):
        for v in (0.1, 0.3, 0.55, 0.9):
            self.assertLessEqual(abs(pwm_minimum(v, 0.4, 0.55)), 0.55 + 1e-9)
        self.assertAlmostEqual(pwm_minimum(0.55, 0.4, 0.55), 0.55)

    def test_monotone(self):
        vals = [pwm_minimum(x / 20 * 0.75, 0.4, 0.75) for x in range(1, 21)]
        self.assertEqual(vals, sorted(vals))


class TestEtat(unittest.TestCase):
    def test_libelles(self):
        self.assertEqual(etat_texte(0, 0), "STOP")
        self.assertEqual(etat_texte(0.5, 0.5), "AVANCE")
        self.assertEqual(etat_texte(-0.5, -0.5), "RECULE")
        self.assertEqual(etat_texte(-0.4, 0.4), "TOURNE GAUCHE")
        self.assertEqual(etat_texte(0.4, -0.4), "TOURNE DROITE")


if __name__ == "__main__":
    unittest.main()
