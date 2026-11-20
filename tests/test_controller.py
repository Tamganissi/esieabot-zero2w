"""Tests de la lecture manette et de la boucle robot en simulation (sans matériel).
Un tube (os.pipe) remplace /dev/input/js0 : les octets sont au format réel js_event."""
import json
import os
import struct
import sys
import unittest

ICI = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ICI, "..", "src"))
import controller  # noqa: E402
from controller import Manette, ManettePerdue  # noqa: E402

AXE, BTN, INIT = 0x02, 0x01, 0x80


def evt(typ, num, val):
    return struct.pack("IhBB", 0, val, typ, num)


class FausseManette:
    """Crée une Manette branchée sur un tube."""
    def __init__(self):
        self.r, self.w = os.pipe()
        os.set_blocking(self.r, False)
        self.m = Manette("tube", fd=self.r)

    def envoyer(self, *evts):
        os.write(self.w, b"".join(evts))


@unittest.skipUnless(sys.platform.startswith("linux"), "select() sur un tube : Linux uniquement (le robot)")
class TestManette(unittest.TestCase):
    def test_axes_normalises(self):
        f = FausseManette()
        f.envoyer(evt(AXE, 1, -32767), evt(AXE, 0, 16384))
        f.m.lire(0.1)
        self.assertAlmostEqual(f.m.axe(1), -1.0)
        self.assertAlmostEqual(f.m.axe(0), 0.5, places=3)

    def test_bouton_et_init(self):
        f = FausseManette()
        f.envoyer(evt(BTN | INIT, 2, 0), evt(BTN, 2, 1))
        evts = f.m.lire(0.1)
        self.assertEqual(evts[0][3], True)    # événement d'initialisation
        self.assertEqual(evts[1][:3], (BTN, 2, 1))
        self.assertEqual(f.m.boutons[2], 1)

    def test_debranchement_detecte(self):
        f = FausseManette()
        os.close(f.w)                          # dongle retiré -> fin de flux
        with self.assertRaises(ManettePerdue):
            f.m.lire(0.1)


@unittest.skipUnless(sys.platform.startswith("linux"), "select() sur un tube : Linux uniquement (le robot)")
class TestRobotSimulation(unittest.TestCase):
    """Boucle complète avec moteurs simulés : vérifie les sécurités de bout en bout."""

    def setUp(self):
        import main
        with open(os.path.join(ICI, "..", "config", "controller.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.f = FausseManette()
        controller_trouver = controller.trouver_peripherique
        main.trouver_peripherique = lambda *_: "tube"
        self.addCleanup(setattr, main, "trouver_peripherique", controller_trouver)
        main.Manette = lambda _chemin: self.f.m
        self.r = main.Robot(cfg, simulation=True, avec_oled=False)
        self.b = cfg["manette"]["boutons"]
        self.ax = cfg["manette"]["axes"]

    def tourner(self, n=40):
        for _ in range(n):
            self.r.pas_de_boucle()

    def test_reste_arrete_sans_bouton_A(self):
        self.f.envoyer(evt(AXE, self.ax["gauche_y"], -32767))
        self.tourner()
        self.assertEqual(self.r.moteurs.dernier, (0.0, 0.0))

    def test_avance_apres_A_puis_urgence(self):
        self.tourner(2)
        self.f.envoyer(evt(BTN, self.b["A"], 1))
        self.tourner(2)
        self.f.envoyer(evt(AXE, self.ax["gauche_y"], -32767))   # joystick en haut = avant
        self.tourner(60)
        g, d = self.r.moteurs.dernier
        self.assertGreater(g, 0.3)
        self.assertAlmostEqual(g, d)
        self.assertLessEqual(g, self.r.vmax + 1e-9)               # limitation de vitesse
        self.f.envoyer(evt(BTN, self.b["START"], 1))
        self.tourner(1)
        self.assertEqual(self.r.moteurs.dernier, (0.0, 0.0))     # arrêt immédiat
        self.tourner(20)
        self.assertEqual(self.r.moteurs.dernier, (0.0, 0.0))     # reste verrouillé

    def test_A_refuse_si_joystick_pousse(self):
        self.tourner(2)
        self.f.envoyer(evt(AXE, self.ax["gauche_y"], -32767), evt(BTN, self.b["A"], 1))
        self.tourner(30)
        self.assertEqual(self.r.moteurs.dernier, (0.0, 0.0))

    def test_perte_manette_arrete(self):
        self.tourner(2)
        self.f.envoyer(evt(BTN, self.b["A"], 1))          # armer joystick au centre
        self.tourner(2)
        self.f.envoyer(evt(AXE, self.ax["gauche_y"], -32767))
        self.tourner(30)
        self.assertNotEqual(self.r.moteurs.dernier, (0.0, 0.0))
        os.close(self.f.w)
        import main
        main.trouver_peripherique = lambda *_: None               # dongle absent
        self.tourner(1)
        self.assertEqual(self.r.moteurs.dernier, (0.0, 0.0))
        self.assertIsNone(self.r.manette)


if __name__ == "__main__":
    unittest.main()
