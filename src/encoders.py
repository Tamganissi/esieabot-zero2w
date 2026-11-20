"""encoders.py — Capteurs de vitesse optiques (modules verts sous le châssis).

Add-on Board v2 : gauche = GPIO24, droit = GPIO16 (doc officielle ; GPIO4 pour la v1 rév. ≤ C).
Comme dans add-on-board-test.py officiel : pull-down et comptage des fronts montants + descendants.
Repère officiel : ~450 fronts/s moteur à pleine vitesse ; < 150 = moteur ou capteur en défaut.
"""
import logging
import threading
import time

log = logging.getLogger("encoders")


class CapteursVitesse:
    def __init__(self, cfg, chip=0):
        import lgpio
        self.lg = lgpio
        self.pins = {"gauche": int(cfg["capteurs_vitesse"]["gauche"]),
                     "droit": int(cfg["capteurs_vitesse"]["droit"])}
        self.h = lgpio.gpiochip_open(chip)
        self.compte = {k: 0 for k in self.pins}
        self._verrou = threading.Lock()
        self._cbs = []
        for nom, pin in self.pins.items():
            lgpio.gpio_claim_alert(self.h, pin, lgpio.BOTH_EDGES, lgpio.SET_PULL_DOWN)
            self._cbs.append(lgpio.callback(self.h, pin, lgpio.BOTH_EDGES, self._fabrique(nom)))
        self._t0 = time.monotonic()
        self._dernier = dict(self.compte)

    def _fabrique(self, nom):
        def cb(_chip, _gpio, _level, _tick):
            with self._verrou:
                self.compte[nom] += 1
        return cb

    def vitesses(self):
        """Fronts par seconde depuis le dernier appel."""
        t = time.monotonic()
        dt = max(1e-3, t - self._t0)
        with self._verrou:
            res = {k: (self.compte[k] - self._dernier[k]) / dt for k in self.pins}
            self._dernier = dict(self.compte)
        self._t0 = t
        return res

    def fermer(self):
        for cb in self._cbs:
            try:
                cb.cancel()
            except Exception:
                pass
        for pin in self.pins.values():
            try:
                self.lg.gpio_free(self.h, pin)
            except Exception:
                pass
        self.lg.gpiochip_close(self.h)


class CapteursAbsents:
    def vitesses(self):
        return {"gauche": 0.0, "droit": 0.0}

    def fermer(self):
        pass
