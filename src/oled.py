"""oled.py — Affichage d'état sur l'OLED SSD1306 128x64 (I2C 0x3C, confirmé par le code officiel esieabot-display).

Tourne dans un thread séparé : une erreur ou une lenteur I2C ne bloque JAMAIS la commande des moteurs.
persist=True : luma n'efface pas l'écran à la fermeture (c'était la cause de « l'écran reste noir »).
"""
import logging
import threading
import time

log = logging.getLogger("oled")


class EcranOLED:
    def __init__(self, cfg):
        o = cfg["oled"]
        self.periode = 1.0 / float(o.get("rafraichissement_max_hz", 4))
        self._donnees = None
        self._affiche = None
        self._evt = threading.Event()
        self._stop = False
        self.ok = False
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from PIL import ImageFont
            self.device = ssd1306(i2c(port=1, address=int(o["adresse_i2c"])),
                                  width=int(o["largeur"]), height=int(o["hauteur"]))
            self.device.persist = True
            try:
                self.f_titre = ImageFont.load_default(size=14)
                self.f_txt = ImageFont.load_default(size=11)
            except TypeError:
                self.f_titre = self.f_txt = ImageFont.load_default()
            self.ok = True
        except Exception as e:
            log.error("OLED indisponible (%s) : le robot fonctionne sans écran", e)
            return
        self._t = threading.Thread(target=self._boucle, name="oled", daemon=True)
        self._t.start()

    def maj(self, etat, manette, vitesse_pct, mode):
        d = (etat, manette, int(round(vitesse_pct)), mode)
        if d != self._donnees:
            self._donnees = d
            self._evt.set()

    def _dessiner(self, d):
        from luma.core.render import canvas
        etat, manette, vit, mode = d
        with canvas(self.device) as c:
            c.text((0, 0), "ESIEABOT", font=self.f_titre, fill="white")
            c.line((0, 17, 127, 17), fill="white")
            c.text((0, 20), f"État : {etat}", font=self.f_txt, fill="white")
            c.text((0, 31), f"Manette : {manette}", font=self.f_txt, fill="white")
            c.text((0, 42), f"Vitesse : {vit} %", font=self.f_txt, fill="white")
            c.text((0, 53), f"Mode : {mode}", font=self.f_txt, fill="white")

    def _boucle(self):
        while not self._stop:
            self._evt.wait(1.0)
            self._evt.clear()
            d = self._donnees
            if d is None or d == self._affiche:
                continue
            try:
                self._dessiner(d)
                self._affiche = d
            except Exception as e:
                log.warning("écriture OLED échouée : %s", e)
            time.sleep(self.periode)

    def message(self, ligne1, ligne2=""):
        if not self.ok:
            return
        from luma.core.render import canvas
        try:
            with canvas(self.device) as c:
                c.text((0, 0), "ESIEABOT", font=self.f_titre, fill="white")
                c.line((0, 17, 127, 17), fill="white")
                c.text((0, 24), ligne1, font=self.f_txt, fill="white")
                c.text((0, 40), ligne2, font=self.f_txt, fill="white")
        except Exception as e:
            log.warning("écriture OLED échouée : %s", e)

    def fermer(self, message="ARRET"):
        self._stop = True
        self._evt.set()
        self.message("État : " + message, "Moteurs coupés")
