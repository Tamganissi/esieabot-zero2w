#!/usr/bin/env python3
"""web.py — Pilotage de l'ESIEAbot depuis un téléphone ou un ordinateur (navigateur web).

Solution de remplacement quand la manette sans fil ne communique pas avec son dongle.
Aucune application à installer : le téléphone/PC ouvre une page web servie par le robot.

Usage :
  python src/web.py --simulation   # page + écran, AUCUNE broche moteur touchée
  python src/web.py                # pilotage réel (roues soulevées pour les premiers essais !)
Puis, sur un appareil connecté au même Wi-Fi que le robot :
  http://pizero2w.local:8080   (ou http://<adresse IP du robot>:8080)
Le code d'accès à 4 chiffres est affiché sur l'écran OLED du robot et dans le journal.

Sécurité (identique au programme manette, plus une « homme mort » réseau) :
  - démarrage DÉSARMÉ ; ARMER seulement joystick au centre ; seul l'appareil qui a armé pilote ;
  - la page envoie la consigne 10 fois/s ; plus de consigne depuis 0,5 s -> moteurs à 0 ;
    plus de contact depuis 2 s (Wi-Fi coupé, page fermée, téléphone verrouillé) -> DÉSARMÉ ;
  - STOP et ARRÊT D'URGENCE acceptés depuis n'importe quel appareil connaissant le code ;
  - toutes les commandes moteur sont exécutées dans la boucle principale (un seul fil d'exécution).
"""
import argparse
import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, ICI)

import socket  # noqa: E402

from main import charger_config, config_logs  # noqa: E402


class ServeurDoublePile(ThreadingHTTPServer):
    """Écoute en IPv6 ET en IPv4 : pizero2w.local peut se résoudre en adresse IPv6 sur le PC."""
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()
from safety import Securite, etat_texte, melange_arcade, pwm_minimum, rampe, zone_morte  # noqa: E402

log = logging.getLogger("web")

DELAI_CONSIGNE_S = 0.5   # consigne plus vieille -> moteurs à 0
DELAI_CONTACT_S = 2.0    # aucun contact -> désarmement


def borne(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(-1.0, min(1.0, v))


class Partage:
    """État partagé entre le serveur web (threads) et la boucle moteur."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.x = self.y = 0.0
        self.t_cmd = 0.0
        self.t_contact = 0.0
        self.id_cmd = None
        self.actions = []        # (action, id) traitées par la boucle principale
        self.statut = {}


class RobotWeb:
    def __init__(self, cfg, simulation=False, avec_oled=True, code=None):
        self.cfg = cfg
        self.sim = simulation
        c = cfg["conduite"]
        self.dz = float(c["zone_morte"])
        self.vmax = float(c["vitesse_max_autorisee"])
        self.vmin = float(c.get("pwm_minimum", 0.0))
        self.limite = self.vmax
        self.profils = c["profils"]
        self.profil = c["profil_initial"]
        self.periode = float(cfg["securite"]["periode_boucle_s"])
        self.pas = float(c["rampe_par_seconde"]) * self.periode
        self.code = code or f"{secrets.randbelow(10000):04d}"

        from motor import MoteursDRV8411, MoteursSimules
        from power import CarteAlim
        self.moteurs = MoteursSimules() if simulation else MoteursDRV8411(cfg)
        self.moteurs.arret()
        self.alim = CarteAlim(cfg)
        self.oled = None
        if avec_oled and cfg["oled"]["actif"]:
            from oled import EcranOLED
            self.oled = EcranOLED(cfg)
            if not self.oled.ok:
                self.oled = None

        self.p = Partage()
        self.sec = Securite()
        self.sec.desarmer("attente téléphone")
        self.pilote = None
        self.g = self.d = 0.0
        self.a_roule = False
        self.dernier_etat = None
        self.t_alim = 0.0
        self.vbat = None

    # ------------------------------------------------------------ actions
    def _action(self, action, ident, x, y, frais):
        if action == "urgence":
            self.sec.arret_urgence("URGENCE (web)")
            self._couper(alim=True)
            self.pilote = None
            log.warning("ARRÊT D'URGENCE (web, appareil %s)", ident)
        elif action == "stop":
            self.sec.desarmer("STOP")
            self._couper()
            self.pilote = None
            log.info("STOP (web, appareil %s)", ident)
        elif action == "armer":
            centre = frais and abs(x) <= self.dz and abs(y) <= self.dz
            if self.sec.armer(centre):
                self.pilote = ident
                self.a_roule = False
                if self.cfg["carte_alimentation"]["activer_moteurs_a_l_armement"] and not self.sim:
                    self.alim.moteurs(True)
                log.info("ARMÉ depuis le web (appareil %s, profil %s)", ident, self.profil)
            else:
                log.info("armement refusé : %s", self.sec.raison if frais else "pas de liaison")
        elif action in ("lent", "normal"):
            self.profil = action.upper()
            log.info("profil %s", self.profil)

    def _couper(self, alim=False):
        self.moteurs.arret()
        self.g = self.d = 0.0
        if alim and not self.sim:
            self.alim.moteurs(False)

    # ------------------------------------------------------------ boucle
    def pas_de_boucle(self):
        maintenant = time.monotonic()
        with self.p.verrou:
            x, y, t_cmd, t_contact, id_cmd = self.p.x, self.p.y, self.p.t_cmd, self.p.t_contact, self.p.id_cmd
            actions, self.p.actions = self.p.actions, []
        frais = maintenant - t_cmd <= DELAI_CONSIGNE_S
        for action, ident in actions:
            self._action(action, ident, x if ident == id_cmd else 1.0, y, frais)

        if self.sec.arme and maintenant - t_contact > DELAI_CONTACT_S:
            self.sec.desarmer("liaison perdue")
            self._couper()
            self.pilote = None
            log.warning("LIAISON PERDUE (%.1f s sans contact) : moteurs arrêtés, robot désarmé",
                        maintenant - t_contact)

        cg = cd = 0.0
        if frais and id_cmd is not None and id_cmd == self.pilote:
            gaz = zone_morte(y, self.dz)
            vir = zone_morte(x, self.dz)
            limite = min(float(self.profils[self.profil]), self.vmax)
            gl, dr = melange_arcade(gaz, vir, float(self.cfg["conduite"]["gain_virage"]))
            self.limite = limite
            cg, cd = gl * limite, dr * limite

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
            etat = "STOP" if self.sec.raison == "STOP" else "APPUYER ARMER"
        else:
            etat = etat_texte(self.g, self.d)
            if etat != "STOP":
                self.a_roule = True
            elif not self.a_roule:
                etat = "PRÊT"
        if etat != self.dernier_etat:
            log.info("état %s (g=%.2f d=%.2f)", etat, self.g, self.d)
            self.dernier_etat = etat
        lien = "TEL OK" if maintenant - t_contact <= DELAI_CONTACT_S else "ATTENTE"
        vit = max(abs(self.g), abs(self.d)) * 100.0
        if self.oled:
            self.oled.maj(etat, lien, vit, f"CODE {self.code}")

        if self.alim.present and maintenant - self.t_alim > 2.0:
            self.t_alim = maintenant
            try:
                self.vbat = round(self.alim.vbat(), 2)
            except Exception:
                self.vbat = None
            if self.alim.demande_extinction():
                log.warning("la carte d'alimentation demande l'extinction (batterie)")
                self.fermer()
                subprocess.call(["sudo", "-n", "systemctl", "poweroff"])

        with self.p.verrou:
            self.p.statut = {"etat": etat, "arme": self.sec.arme, "urgence": self.sec.urgence,
                             "raison": self.sec.raison, "pilote": self.pilote, "profil": self.profil,
                             "vitesse": round(vit), "vbat": self.vbat, "simulation": self.sim}
        time.sleep(self.periode)

    def fermer(self):
        try:
            self.moteurs.arret()
        finally:
            self.g = self.d = 0.0
            if not self.sim:
                self.alim.moteurs(False)
            self.moteurs.fermer()
            if self.oled:
                self.oled.fermer("ARRÊT")


def fabrique_handler(robot):
    page = open(os.path.join(ICI, "web_page.html"), "rb").read()
    p = robot.p

    class H(BaseHTTPRequestHandler):
        server_version = "esieabot"

        def log_message(self, *_a):  # pas de journal par requête (10/s)
            pass

        def _json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
            elif u.path == "/api/etat":
                if parse_qs(u.query).get("code", [""])[0] != robot.code:
                    return self._json(403, {"erreur": "code"})
                with p.verrou:
                    self._json(200, dict(p.statut))
            else:
                self._json(404, {"erreur": "inconnu"})

        def do_POST(self):
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 1000)
                req = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"erreur": "json"})
            if not isinstance(req, dict) or str(req.get("code", "")) != robot.code:
                return self._json(403, {"erreur": "code"})
            ident = str(req.get("id", ""))[:32] or "?"
            u = urlparse(self.path).path
            maintenant = time.monotonic()
            with p.verrou:
                p.t_contact = maintenant if ident == robot.pilote or robot.pilote is None else p.t_contact
                if u == "/api/cmd":
                    if robot.pilote is None or ident == robot.pilote:
                        p.x, p.y = borne(req.get("x")), borne(req.get("y"))
                        p.t_cmd, p.id_cmd = maintenant, ident
                elif u == "/api/action":
                    a = str(req.get("action", ""))
                    if a not in ("armer", "stop", "urgence", "lent", "normal"):
                        return self._json(400, {"erreur": "action"})
                    if a == "armer" and robot.pilote not in (None, ident):
                        return self._json(409, {"erreur": "un autre appareil pilote déjà"})
                    p.actions.append((a, ident))
                else:
                    return self._json(404, {"erreur": "inconnu"})
                st = dict(p.statut)
            st["moi_pilote"] = st.get("pilote") == ident
            self._json(200, st)

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(RACINE, "config", "controller.json"))
    ap.add_argument("--simulation", action="store_true", help="ne touche à aucune broche moteur")
    ap.add_argument("--sans-oled", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--code", help="code d'accès fixe (sinon 4 chiffres aléatoires à chaque démarrage)")
    ap.add_argument("--duree", type=float, default=0, help="arrêt automatique après N secondes (tests)")
    a = ap.parse_args()

    config_logs()
    cfg = charger_config(a.config)

    def sortie(signum, _frame):
        raise SystemExit(f"signal {signum}")
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, sortie)

    robot = RobotWeb(cfg, simulation=a.simulation, avec_oled=not a.sans_oled, code=a.code)
    serveur = ServeurDoublePile(("::", a.port), fabrique_handler(robot))
    serveur.daemon_threads = True
    threading.Thread(target=serveur.serve_forever, name="http", daemon=True).start()
    log.info("démarrage web (%s) port %d — CODE D'ACCÈS : %s — moteurs à l'arrêt, désarmé",
             "SIMULATION" if a.simulation else "RÉEL", a.port, robot.code)
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
        serveur.shutdown()
        robot.fermer()
        log.info("moteurs arrêtés, programme web terminé")


if __name__ == "__main__":
    main()
