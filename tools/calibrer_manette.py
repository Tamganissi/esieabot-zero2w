#!/usr/bin/env python3
"""calibrer_manette.py — Identifie RÉELLEMENT les numéros d'axes et de boutons de la manette ESIEA
et met à jour config/controller.json (une sauvegarde .bak horodatée est créée avant).

Usage (dans le terminal SSH, la manette allumée et le dongle branché) :
  cd ~/esieabot && venv/bin/python tools/calibrer_manette.py
Aucun moteur n'est commandé par ce programme.
"""
import json
import os
import shutil
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "src"))
from controller import JS_EVENT_AXIS, JS_EVENT_BUTTON, Manette, trouver_peripherique  # noqa: E402

CFG = os.path.join(RACINE, "config", "controller.json")
BOUTONS = ["A", "B", "X", "Y", "SELECT", "START"]
AXES = [("gauche_y", "Poussez le joystick GAUCHE vers le HAUT et maintenez"),
        ("gauche_x", "Poussez le joystick GAUCHE vers la DROITE et maintenez"),
        ("droit_y", "Poussez le joystick DROIT vers le HAUT et maintenez"),
        ("droit_x", "Poussez le joystick DROIT vers la DROITE et maintenez"),
        ("croix_y", "Appuyez sur la CROIX vers le HAUT et maintenez"),
        ("croix_x", "Appuyez sur la CROIX vers la DROITE et maintenez")]


def vider(m):
    fin = time.monotonic() + 0.3
    while time.monotonic() < fin:
        m.lire(0.05)


def attendre_bouton(m, nom):
    print(f"  -> Appuyez sur {nom} (ou attendez 10 s pour passer)")
    vider(m)
    fin = time.monotonic() + 10
    while time.monotonic() < fin:
        for typ, num, val, init in m.lire(0.1):
            if typ == JS_EVENT_BUTTON and val == 1 and not init:
                print(f"     {nom} = bouton {num}")
                return num
    print(f"     {nom} : non détecté, valeur actuelle conservée")
    return None


def attendre_axe(m, consigne):
    print(f"  -> {consigne} (10 s max)")
    vider(m)
    repos = dict(m.axes)
    fin = time.monotonic() + 10
    while time.monotonic() < fin:
        m.lire(0.1)
        for num, v in m.axes.items():
            if abs(v - repos.get(num, 0.0)) > 0.7:
                print(f"     axe {num}, valeur {v:+.2f}")
                time.sleep(0.8)
                print("     relâchez")
                return num, v
    print("     non détecté, valeur actuelle conservée")
    return None, None


def main():
    chemin = trouver_peripherique()
    if not chemin:
        sys.exit("Aucune manette (/dev/input/js*). Branchez le dongle (adaptateur OTG) et allumez la manette.")
    m = Manette(chemin)
    print(f"Manette : {chemin} — {m.nom}\nAucun moteur ne sera commandé.\n")
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    mc = cfg["manette"]

    print("BOUTONS")
    for nom in BOUTONS:
        n = attendre_bouton(m, nom)
        if n is not None:
            mc["boutons"][nom] = n
    print("\nAXES")
    for cle, consigne in AXES:
        n, v = attendre_axe(m, consigne)
        if n is not None:
            mc["axes"][cle] = n
            if cle == "gauche_y":
                mc["inverser_y"] = v < 0   # haut négatif -> on inverse pour que haut = avancer

    doublons = [n for n in mc["boutons"].values() if list(mc["boutons"].values()).count(n) > 1]
    if doublons:
        print(f"\nATTENTION : un même numéro est affecté à plusieurs boutons : {sorted(set(doublons))}")
    bak = CFG + time.strftime(".%Y%m%d_%H%M%S.bak")
    shutil.copy2(CFG, bak)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"\nConfiguration enregistrée ({CFG}), sauvegarde : {bak}")
    print(json.dumps(mc, indent=2, ensure_ascii=False))
    m.fermer()


if __name__ == "__main__":
    main()
