"""Tests de la télécommande web (sans matériel : moteurs simulés, sans OLED, sans réseau).
On remplit directement l'état partagé comme le ferait le serveur HTTP."""
import json
import os
import sys
import time
import unittest

ICI = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ICI, "..", "src"))
import web  # noqa: E402


def nouveau_robot():
    with open(os.path.join(ICI, "..", "config", "controller.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    r = web.RobotWeb(cfg, simulation=True, avec_oled=False, code="1234")
    r.alim.present = False  # pas d'I2C pendant les tests
    return r


def consigne(r, ident, x, y, age=0.0):
    with r.p.verrou:
        t = time.monotonic() - age
        r.p.x, r.p.y, r.p.t_cmd, r.p.id_cmd, r.p.t_contact = x, y, t, ident, t


def action(r, a, ident):
    with r.p.verrou:
        r.p.actions.append((a, ident))


class TestWeb(unittest.TestCase):
    def test_borne(self):
        self.assertEqual(web.borne(5), 1.0)
        self.assertEqual(web.borne(-5), -1.0)
        self.assertEqual(web.borne("x"), 0.0)
        self.assertEqual(web.borne(float("nan")), 0.0)

    def test_demarre_desarme_et_ignore_consigne(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 1)
        r.pas_de_boucle()
        self.assertFalse(r.sec.arme)
        self.assertEqual((r.g, r.d), (0.0, 0.0))

    def test_armement_refuse_si_joystick_pousse(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 1)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        self.assertFalse(r.sec.arme)

    def test_armement_refuse_sans_consigne_recente(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 0, age=1.0)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        self.assertFalse(r.sec.arme)

    def test_conduite_puis_consigne_perimee(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 0)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        self.assertTrue(r.sec.arme)
        for _ in range(20):
            consigne(r, "tel", 0, 1)
            r.pas_de_boucle()
        self.assertGreater(r.g, 0)
        self.assertGreater(r.d, 0)
        consigne(r, "tel", 0, 1, age=web.DELAI_CONSIGNE_S + 0.1)
        r.pas_de_boucle()
        self.assertEqual((r.g, r.d), (0.0, 0.0))

    def test_liaison_perdue_desarme(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 0)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        consigne(r, "tel", 0, 0, age=web.DELAI_CONTACT_S + 0.1)
        r.pas_de_boucle()
        self.assertFalse(r.sec.arme)
        self.assertEqual(r.sec.raison, "liaison perdue")

    def test_seul_le_pilote_conduit(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 0)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        for _ in range(10):
            consigne(r, "intrus", 0, 1)
            r.pas_de_boucle()
        self.assertEqual((r.g, r.d), (0.0, 0.0))

    def test_urgence_verrouillee(self):
        r = nouveau_robot()
        consigne(r, "tel", 0, 0)
        action(r, "armer", "tel")
        r.pas_de_boucle()
        action(r, "urgence", "autre")
        r.pas_de_boucle()
        self.assertTrue(r.sec.urgence)
        consigne(r, "tel", 0, 1)
        r.pas_de_boucle()
        self.assertEqual((r.g, r.d), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
