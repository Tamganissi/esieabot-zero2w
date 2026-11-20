#!/usr/bin/env python3
"""main.py — Pilotage de l'ESIEAbot avec la manette sans fil ESIEA.

Usage :
  python src/main.py --simulation   # manette + écran, AUCUNE broche moteur touchée
  python src/main.py                # pilotage réel (roues soulevées pour les premiers essais !)

Commandes (par défaut, voir config/controller.json) :
  A      : armer (joysticks au centre)        B      : stop (désarme)
  START  : arrêt d'urgence verrouillé          SELECT : mode MANUEL <-> DUAL
  X      : profil LENT                         Y      : profil NORMAL
  Joystick gauche : gaz (haut/bas) + virage (gauche/droite) en mode MANUEL
  Mode DUAL : joystick gauche = gaz, joystick droit = virage (comme esieabot-pwm officiel)
  Croix : déplacements lents de secours
"""
import argparse
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, ICI)

from controller import JS_EVENT_BUTTON, Manette, ManettePerdue, trouver_peripherique  # noqa: E402
from safety import Securite, etat_texte, melange_arcade, pwm_minimum, rampe, zone_morte  # noqa: E402

log = logging.getLogger("esieabot")


def config_logs():
    os.makedirs(os.path.join(RACINE, "logs"), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)-8s %(message)s")
    fichier = logging.handlers.RotatingFileHandler(
        os.path.join(RACINE, "logs", "esieabot.log"), maxBytes=1_000_000, backupCount=3)
    fichier.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fichier, console])


def charger_config(chemin):
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


class Robot:
    def __init__(self, cfg, simulation=False, avec_oled=True):
        self.cfg = cfg
        self.sim = simulation
        c = cfg["conduite"]
        self.dz = float(c["zone_morte"])
        self.vmax = float(c["vitesse_max_autorisee"])
        self.vmin = float(c.get("pwm_minimum", 0.0))
        self.limite = self.vmax
        self.profils = c["profils"]
        self.profil = c["profil_initial"]
        self.modes = c["modes"]
        self.mode_i = 0
        self.periode = float(cfg["securite"]["periode_boucle_s"])
        self.pas = float(c["rampe_par_seconde"]) * self.periode
        self.timeout = float(cfg["securite"]["timeout_inactivite_s"])
        self.ax = cfg["manette"]["axes"]
        self.bt = {v: k for k, v in cfg["manette"]["boutons"].items()}  # numéro -> nom
        self.inv_y = bool(cfg["manette"]["inverser_y"])

        from motor import MoteursDRV8411, MoteursSimules
        from encoders import CapteursAbsents, CapteursVitesse
        from power import CarteAlim
        self.moteurs = MoteursSimules() if simulation else MoteursDRV8411(cfg)
        self.moteurs.arret()
        self.capteurs = CapteursAbsents()
        if not simulation:
            try:
                self.capteurs = CapteursVitesse(cfg)
            except Exception as e:
                log.warning("capteurs de vitesse indisponibles : %s", e)
        self.alim = CarteAlim(cfg)
        self.oled = None
        if avec_oled and cfg["oled"]["actif"]:
            from oled import EcranOLED
            self.oled = EcranOLED(cfg)
            if not self.oled.ok:
                self.oled = None

        self.sec = Securite()
        self.manette = None
        self.g = self.d = 0.0
        self.a_roule = False
        self.dernier_evt = time.monotonic()
        self.dernier_etat = None
        self.t_alim = 0.0

    # ------------------------------------------------------------------ manette
    def _connecter(self):
        chemin = trouver_peripherique(self.cfg["manette"]["peripherique"])
        if not chemin:
            return False
        try:
            self.manette = Manette(chemin)
        except OSError as e:
            log.warning("ouverture %s impossible : %s", chemin, e)
            return False
        self.sec.desarmer("manette connectée : appuyer sur A")
        log.info("manette connectée : %s (%s)", chemin, self.manette.nom)
        return True

    def _perdre_manette(self, raison):
        self.moteurs.arret()
        self.g = self.d = 0.0
        self.sec.desarmer("manette perdue")
        log.warning("MANETTE PERDUE (%s) : moteurs arrêtés", raison)
        if self.manette:
            self.manette.fermer()
        self.manette = None

    def _centres(self):
        m = self.manette
        return all(abs(m.axe(self.ax[k])) <= self.dz for k in ("gauche_x", "gauche_y", "droit_x"))

    def _bouton(self, num):
        nom = self.bt.get(num)
        if nom == "START":
            self.sec.arret_urgence("START")
            self.moteurs.arret()
            self.g = self.d = 0.0
            self.alim.moteurs(False)
            log.warning("ARRÊT D'URGENCE (START)")
        elif nom == "B":
            self.sec.desarmer("STOP (B)")
            self.moteurs.arret()
            self.g = self.d = 0.0
            log.info("STOP (B)")
        elif nom == "A":
            if self.sec.armer(self._centres()):
                if self.cfg["carte_alimentation"]["activer_moteurs_a_l_armement"] and not self.sim:
                    self.alim.moteurs(True)
                log.info("ARMÉ (profil %s, mode %s)", self.profil, self.modes[self.mode_i])
            else:
                log.info("armement refusé : %s", self.sec.raison)
        elif nom == "X":
            self.profil = "LENT"
            log.info("profil LENT")
        elif nom == "Y":
            self.profil = "NORMAL"
            log.info("profil NORMAL")
        elif nom == "SELECT":
            self.mode_i = (self.mode_i + 1) % len(self.modes)
            log.info("mode %s", self.modes[self.mode_i])
        else:
            log.info("bouton %d (non affecté)", num)

    # ------------------------------------------------------------------ consignes
    def _cible(self):
        m = self.manette
        sy = -1.0 if self.inv_y else 1.0
        gaz = sy * zone_morte(m.axe(self.ax["gauche_y"]), self.dz)
        if self.modes[self.mode_i] == "DUAL":
            vir = zone_morte(m.axe(self.ax["droit_x"]), self.dz)
        else:
            vir = zone_morte(m.axe(self.ax["gauche_x"]), self.dz)
        limite = min(float(self.profils[self.profil]), self.vmax)
        if gaz == 0.0 and vir == 0.0:
            cx = m.axe(self.ax["croix_x"])
            cy = sy * m.axe(self.ax["croix_y"])
            if abs(cx) > 0.5 or abs(cy) > 0.5:
                gaz = 1.0 if cy > 0.5 else (-1.0 if cy < -0.5 else 0.0)
                vir = 1.0 if cx > 0.5 else (-1.0 if cx < -0.5 else 0.0)
                limite = min(float(self.cfg["conduite"]["vitesse_croix"]), self.vmax)
        gl, dr = melange_arcade(gaz, vir, float(self.cfg["conduite"]["gain_virage"]))
        self.limite = limite
        return gl * limite, dr * limite

    # ------------------------------------------------------------------ boucle
    def pas_de_boucle(self):
        if self.manette is None:
            self.moteurs.arret()
            self.g = self.d = 0.0
            if not self._connecter():
                self._afficher("ATTENTE MANETTE", "ABSENTE")
                time.sleep(0.5)
                return
        try:
            evts = self.manette.lire(self.periode)
        except ManettePerdue as e:
            self._perdre_manette(e)
            return
        maintenant = time.monotonic()
        for typ, num, val, init in evts:
            if not init:
                self.dernier_evt = maintenant
            if typ == JS_EVENT_BUTTON and val == 1 and not init:
                self._bouton(num)

        cg, cd = self._cible()
        if self.timeout > 0 and (cg or cd) and maintenant - self.dernier_evt > self.timeout:
            cg = cd = 0.0
        defaut = self.moteurs.defaut()
        if defaut and self.sec.arme:
            log.error("DÉFAUT DRV8411 (GPIO27 bas) : moteurs arrêtés")
        if not self.sec.peut_rouler(defaut):
            cg = cd = 0.0
            self.g = self.d = 0.0
        self.g = rampe(self.g, cg, self.pas)
        self.d = rampe(self.d, cd, self.pas)
        self.moteurs.commander(pwm_minimum(self.g, self.vmin, self.limite),
                               pwm_minimum(self.d, self.vmin, self.limite))
        self.moteurs.led(self.sec.arme)

        if self.sec.urgence:
            etat = "URGENCE"
        elif defaut:
            etat = "DEFAUT DRV"
        elif not self.sec.arme:
            etat = "STOP" if self.sec.raison == "STOP (B)" else "APPUYER SUR A"
        else:
            etat = etat_texte(self.g, self.d)
            if etat != "STOP":
                self.a_roule = True
            elif not self.a_roule:
                etat = "PRÊT"
        if etat != self.dernier_etat:
            log.info("état %s (g=%.2f d=%.2f)", etat, self.g, self.d)
            self.dernier_etat = etat
        self._afficher(etat, "CONNECTÉE")

        if self.alim.present and maintenant - self.t_alim > 2.0:
            self.t_alim = maintenant
            if self.alim.demande_extinction():
                log.warning("la carte d'alimentation demande l'extinction (batterie)")
                self.arreter_tout()
                if self.oled:
                    self.oled.message("Batterie faible", "Extinction...")
                subprocess.call(["sudo", "-n", "systemctl", "poweroff"])

    def _afficher(self, etat, manette):
        if self.oled:
            vit = max(abs(self.g), abs(self.d)) * 100.0
            self.oled.maj(etat, manette, vit, f"{self.modes[self.mode_i]} {self.profil}")

    def arreter_tout(self):
        try:
            self.moteurs.arret()
        finally:
            self.g = self.d = 0.0
            if not self.sim:
                self.alim.moteurs(False)

    def fermer(self):
        self.arreter_tout()
        self.moteurs.fermer()
        self.capteurs.fermer()
        if self.manette:
            self.manette.fermer()
        if self.oled:
            self.oled.fermer("ARRÊT")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=os.path.join(RACINE, "config", "controller.json"))
    p.add_argument("--simulation", action="store_true", help="ne touche à aucune broche moteur")
    p.add_argument("--sans-oled", action="store_true")
    p.add_argument("--duree", type=float, default=0, help="arrêt automatique après N secondes (tests)")
    a = p.parse_args()

    config_logs()
    cfg = charger_config(a.config)

    def sortie(signum, _frame):
        raise SystemExit(f"signal {signum}")
    signal.signal(signal.SIGTERM, sortie)
    signal.signal(signal.SIGINT, sortie)
    signal.signal(signal.SIGHUP, sortie)

    robot = Robot(cfg, simulation=a.simulation, avec_oled=not a.sans_oled)
    log.info("démarrage (%s) — moteurs à l'arrêt, en attente de la manette puis du bouton A",
             "SIMULATION" if a.simulation else "RÉEL")
    t0 = time.monotonic()
    try:
        while not a.duree or time.monotonic() - t0 < a.duree:
            robot.pas_de_boucle()
    except SystemExit as e:
        log.info("arrêt demandé : %s", e)
    except Exception:
        log.exception("ERREUR INATTENDUE : arrêt des moteurs")
        raise
    finally:
        robot.fermer()
        log.info("moteurs arrêtés, programme terminé")


if __name__ == "__main__":
    main()
