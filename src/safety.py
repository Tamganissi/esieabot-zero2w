"""safety.py — Règles de sécurité et calcul des consignes (logique pure, testable sans matériel).

États :
  SECURITE : au démarrage, après arrêt d'urgence ou perte de manette -> moteurs bloqués à 0.
             On en sort avec le bouton A, joysticks au centre uniquement.
  ARME     : la manette pilote les moteurs.
L'arrêt d'urgence (START) est verrouillé : il faut ré-armer avec A.
"""
import math


def zone_morte(v, seuil):
    """0 dans la zone morte, puis remise à l'échelle progressive jusqu'à 1."""
    if abs(v) <= seuil:
        return 0.0
    return math.copysign((abs(v) - seuil) / (1.0 - seuil), v)


def melange_arcade(gaz, virage, gain_virage=0.7):
    """gaz/virage dans [-1, 1] -> (gauche, droit) en conduite différentielle, normalisés."""
    v = virage * gain_virage
    g, d = gaz + v, gaz - v
    m = max(1.0, abs(g), abs(d))
    return g / m, d / m


def rampe(actuel, cible, pas_max):
    """Limite la variation par itération (démarrages et inversions en douceur).
    Exception volontaire : un retour vers 0 est immédiat (freiner n'est jamais limité)."""
    if cible == 0.0:
        return 0.0
    if actuel != 0.0 and math.copysign(1, actuel) != math.copysign(1, cible):
        return 0.0  # inversion de sens : on passe d'abord par 0
    delta = max(-pas_max, min(pas_max, cible - actuel))
    return actuel + delta


def pwm_minimum(v, vmin, limite):
    """Compense le seuil de démarrage des moteurs (mesuré le 19/11/2026 : 30 % ne fait pas tourner
    la roue gauche, 45 % fait tourner les 4 sens).
    v est dans [-limite, limite]. 0 reste 0 ; sinon |sortie| va de vmin (joystick à peine poussé)
    à limite (joystick à fond). La sortie ne dépasse jamais limite."""
    if v == 0.0:
        return 0.0
    if vmin <= 0.0 or limite <= vmin:
        return math.copysign(min(abs(v), limite), v)
    frac = min(1.0, abs(v) / limite)
    return math.copysign(vmin + frac * (limite - vmin), v)


class Securite:
    def __init__(self):
        self.arme = False
        self.urgence = False
        self.raison = "démarrage"

    def armer(self, joysticks_au_centre):
        if not joysticks_au_centre:
            self.raison = "joysticks non centrés"
            return False
        self.arme, self.urgence, self.raison = True, False, ""
        return True

    def arret_urgence(self, raison="START"):
        self.arme, self.urgence, self.raison = False, True, raison

    def desarmer(self, raison):
        self.arme, self.raison = False, raison

    def peut_rouler(self, defaut_driver=False):
        if defaut_driver:
            self.desarmer("défaut DRV8411")
        return self.arme and not self.urgence and not defaut_driver


def etat_texte(gauche, droit, seuil=0.02):
    """Libellé affiché sur l'OLED à partir des consignes appliquées."""
    if abs(gauche) < seuil and abs(droit) < seuil:
        return "STOP"
    if gauche > seuil and droit > seuil:
        if abs(gauche - droit) < 0.15:
            return "AVANCE"
        return "AVANCE GAUCHE" if droit > gauche else "AVANCE DROITE"
    if gauche < -seuil and droit < -seuil:
        return "RECULE"
    return "TOURNE GAUCHE" if droit > gauche else "TOURNE DROITE"
