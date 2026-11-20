"""motor.py — Commande des deux moteurs via le DRV8411 de l'Add-on Board ESIEA.

Principe (identique aux sources officielles esieabot-pwm.c / esieabot.py) :
  chaque moteur a 2 entrées du DRV8411 : AVANT et ARRIERE.
  - avant = PWM, arrière = 0  -> le moteur tourne en avant
  - avant = 0, arrière = PWM  -> le moteur tourne en arrière
  - les deux à 0              -> roue libre (arrêt)
Le Raspberry Pi ne fournit QUE des signaux logiques 3,3 V ; la puissance vient du DRV8411.

Bibliothèque : lgpio (officielle sur Raspberry Pi OS Trixie). pigpiod, utilisé par les
programmes officiels, n'existe plus dans Debian 13.
"""
import logging

log = logging.getLogger("motor")


def borner(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


class MoteursDRV8411:
    """Pilote matériel. Toutes les broches sont mises à 0 à l'ouverture et à la fermeture."""

    def __init__(self, cfg, chip=0):
        import lgpio  # import local : les tests unitaires n'en ont pas besoin
        self.lg = lgpio
        m = cfg["moteurs"]
        self.freq = int(m["frequence_pwm_hz"])
        self.cotes = {
            "gauche": (m["gauche"]["avant"], m["gauche"]["arriere"], bool(m["gauche"]["inverser"])),
            "droit": (m["droit"]["avant"], m["droit"]["arriere"], bool(m["droit"]["inverser"])),
        }
        self.broches = [p for (a, b, _) in self.cotes.values() for p in (a, b)]
        self.h = lgpio.gpiochip_open(chip)
        for p in self.broches:
            lgpio.gpio_claim_output(self.h, p, 0)
        self._duty = {p: 0.0 for p in self.broches}
        # nFAULT du DRV8411 : HAUT = OK, BAS = défaut (surchauffe, surintensité). Pull-up sur la carte.
        self.pin_defaut = int(m["gpio_defaut_drv8411"])
        lgpio.gpio_claim_input(self.h, self.pin_defaut)
        self.pin_led = 26  # LED bleue D1 de l'Add-on Board
        lgpio.gpio_claim_output(self.h, self.pin_led, 0)
        log.info("DRV8411 prêt, broches %s à 0", self.broches)

    def defaut(self):
        """True si le DRV8411 signale un défaut (nFAULT à l'état bas)."""
        return self.lg.gpio_read(self.h, self.pin_defaut) == 0

    def led(self, allumee):
        self.lg.gpio_write(self.h, self.pin_led, 1 if allumee else 0)

    def _couper(self, pin):
        """Coupe le PWM puis force la broche à 0. Chaque étape est tentée indépendamment.
        NB : lgpio 0.2.2 (Trixie) refuse tx_pwm(fréquence=0) -> 'bad PWM micros' (constaté le 18/11/2026) ;
        on arrête donc le PWM avec un rapport cyclique de 0 à la fréquence normale."""
        ok = True
        try:
            self.lg.tx_pwm(self.h, pin, self.freq, 0)
        except Exception as e:
            ok = False
            log.error("arrêt PWM broche %s : %s", pin, e)
        try:
            self.lg.gpio_write(self.h, pin, 0)
        except Exception as e:
            ok = False
            log.error("mise à 0 broche %s : %s", pin, e)
        self._duty[pin] = 0.0
        return ok

    def _pwm(self, pin, duty_pct):
        duty_pct = round(duty_pct, 1)
        if self._duty[pin] == duty_pct:
            return  # évite de relancer le PWM inutilement
        if duty_pct <= 0:
            self._couper(pin)
        else:
            self.lg.tx_pwm(self.h, pin, self.freq, duty_pct)
            self._duty[pin] = duty_pct

    def _cote(self, nom, valeur):
        avant, arriere, inv = self.cotes[nom]
        v = borner(-valeur if inv else valeur)
        duty = abs(v) * 100.0
        if v > 0:
            self._pwm(arriere, 0)          # on coupe d'abord le sens opposé
            self._pwm(avant, duty)
        elif v < 0:
            self._pwm(avant, 0)
            self._pwm(arriere, duty)
        else:
            self._pwm(avant, 0)
            self._pwm(arriere, 0)

    def commander(self, gauche, droit):
        """gauche/droit dans [-1, 1] (1 = 100 % de PWM)."""
        self._cote("gauche", gauche)
        self._cote("droit", droit)

    def arret(self):
        for p in self.broches:  # chaque broche est tentée, même si une autre échoue
            self._couper(p)

    def fermer(self):
        self.arret()
        # Les lignes restent en sortie à 0 après libération ; le service systemd
        # applique en plus un ExecStopPost qui force ces broches à 0 (filet de sécurité).
        try:
            self.led(False)
        except Exception:
            pass
        for p in self.broches + [self.pin_defaut, self.pin_led]:
            try:
                self.lg.gpio_free(self.h, p)
            except Exception:
                pass
        self.lg.gpiochip_close(self.h)
        log.info("DRV8411 libéré")


class MoteursSimules:
    """Remplace le pilote en mode --simulation : aucune broche n'est touchée."""

    def __init__(self, *_a, **_k):
        self.dernier = (0.0, 0.0)

    def defaut(self):
        return False

    def led(self, allumee):
        pass

    def commander(self, gauche, droit):
        self.dernier = (borner(gauche), borner(droit))

    def arret(self):
        self.dernier = (0.0, 0.0)

    def fermer(self):
        self.arret()
