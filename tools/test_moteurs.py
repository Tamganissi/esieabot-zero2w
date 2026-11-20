#!/usr/bin/env python3
"""test_moteurs.py — Test guidé des moteurs, À FAIBLE VITESSE, ROUES SOULEVÉES.

Pour chaque moteur et chaque sens : PWM réduit pendant 1,5 s, comptage des fronts du capteur de vitesse,
contrôle du signal de défaut DRV8411. Inspiré de add-on-board-test.py officiel (mêmes broches, mêmes seuils),
mais à vitesse réduite et sans toucher aux servos.

Usage : cd ~/esieabot && venv/bin/python tools/test_moteurs.py --roues-soulevees [--vitesse 0.30]
Les moteurs sont arrêtés à la fin, en cas d'erreur et sur Ctrl+C.
"""
import argparse
import json
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "src"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--roues-soulevees", action="store_true", required=True,
                   help="confirmation obligatoire : le robot est sur un support, roues libres")
    p.add_argument("--vitesse", type=float, default=0.30)
    p.add_argument("--duree", type=float, default=1.5)
    a = p.parse_args()
    vitesse = max(0.05, min(0.5, a.vitesse))   # bornée à 50 % pour un test

    with open(os.path.join(RACINE, "config", "controller.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    from motor import MoteursDRV8411
    from encoders import CapteursVitesse
    from power import CarteAlim

    alim = CarteAlim(cfg)
    if alim.present:
        print(f"Carte d'alimentation : Vbat={alim.vbat():.2f} V  Vmot avant activation={alim.vmot():.2f} V")
        alim.moteurs(True)
        time.sleep(0.3)
        print(f"Vmot après activation = {alim.vmot():.2f} V")
    else:
        print("Carte d'alimentation NON détectée (0x5A) : les moteurs risquent de ne pas être alimentés.")

    mot = MoteursDRV8411(cfg)
    capt = CapteursVitesse(cfg)
    resultats = []
    try:
        if mot.defaut():
            print("DÉFAUT DRV8411 présent AVANT le test : arrêt.")
            return
        for cote in ("gauche", "droit"):
            for sens, signe in (("avant", 1), ("arrière", -1)):
                consigne = (signe * vitesse, 0.0) if cote == "gauche" else (0.0, signe * vitesse)
                capt.vitesses()
                mot.commander(*consigne)
                time.sleep(a.duree)
                v = capt.vitesses()
                mot.arret()
                defaut = mot.defaut()
                resultats.append((cote, sens, v[cote], v["droit" if cote == "gauche" else "gauche"], defaut))
                print(f"{cote:6s} {sens:8s} : {v[cote]:6.0f} fronts/s (autre roue {resultats[-1][3]:4.0f})"
                      f"{'  DÉFAUT DRV8411 !' if defaut else ''}")
                time.sleep(0.8)
                if defaut:
                    return
    finally:
        mot.arret()
        if alim.present:
            alim.moteurs(False)
        mot.fermer()
        capt.fermer()
        print("Moteurs arrêtés.")

    print("\nBilan (repère officiel : ~450 fronts/s à 100 %, < 150 = problème ; ici vitesse réduite)")
    for cote, sens, n, autre, _ in resultats:
        if n < 20:
            diag = "AUCUNE ROTATION MESURÉE (moteur non alimenté, câblage ou capteur)"
        elif autre > n * 0.5:
            diag = "l'AUTRE roue bouge aussi : capteurs ou moteurs inversés ?"
        else:
            diag = "rotation mesurée"
        print(f"  {cote:6s} {sens:8s} : {diag}")


if __name__ == "__main__":
    main()
