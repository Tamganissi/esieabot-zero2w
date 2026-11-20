# esieabot-zero2w

Pilotage du robot **ESIEAbot** (Add-on Board ESIEA **v2**) sur un **Raspberry Pi Zero 2 W** sous **Raspberry Pi OS Lite 64 bits (Debian 13 Trixie)**, à la manette sans fil ou depuis un navigateur web, avec connexion au PC Windows par **câble USB (réseau + port série)** et par **Wi-Fi**.

## Pourquoi ce projet
Les programmes officiels ESIEAbot reposent sur le démon `pigpiod`, qui **n'existe plus dans Debian 13**. Ce projet reprend leur logique (mêmes broches, même PWM sur le DRV8411, même protocole I2C pour la carte d'alimentation) avec les bibliothèques prises en charge par Trixie : **lgpio** et **smbus2**.

## Contenu
```
config/controller.json     Broches, manette, vitesses, sécurités
src/main.py                Pilotage à la manette (/dev/input/js0)
src/web.py                 Pilotage depuis un téléphone/PC (http://pizero2w.local:8080)
src/motor.py · safety.py · controller.py · encoders.py · oled.py · power.py
tests/                     Tests unitaires, sans matériel
tools/                     Calibration manette, test moteurs, choix du mode USB
systemd/                   Services esieabot / esieabot-web
setup/pi/                  Gadget USB composite NCM + ACM (réseau + console série)
setup/windows/             Écriture cloud-init sur la microSD, détection du Pi
docs/CONNEXION.md          Connecter le Pi Zero 2 W à Windows (USB + Wi-Fi), pas à pas
install.sh                 Installation sur le Pi
```

## Matériel
| Fonction | GPIO (BCM) |
|---|---|
| Moteur gauche AVANT / ARRIÈRE | 23 / 25 |
| Moteur droit AVANT / ARRIÈRE | 22 / 17 |
| Défaut DRV8411 (haut = OK) | 27 |
| Capteurs de vitesse gauche / droit | 24 / 16 |
| Bouton / LED bleue | 6 / 26 |
| I2C : OLED SSD1306 / ADC TLA2024 / gyro ICM-42670-P / carte d'alimentation | 0x3C / 0x48 / 0x68 / 0x5A |

## Installation (sur le Pi)
```bash
git clone https://github.com/<votre-compte>/esieabot-zero2w.git ~/esieabot
cd ~/esieabot
./install.sh            # paquets apt, venv, services systemd (non activés)
```
Pour préparer la carte microSD et la connexion au PC, voir [docs/CONNEXION.md](docs/CONNEXION.md).

## Mise en route
1. Allumer le robot avec sa carte d'alimentation et une batterie **chargée** (les moteurs ne sont alimentés que par elle).
2. Se connecter : `ssh pi-wifi`.
3. Brancher le dongle de la manette sur le port **« USB »** (centre) via un adaptateur OTG. Le port doit être en mode `otg` ou `host` : `sudo tools/usb_mode.sh otg --reboot`.
4. Calibration (une fois) : `venv/bin/python tools/calibrer_manette.py`.
5. Test sans moteurs : `venv/bin/python src/main.py --simulation`.
6. Test moteurs **robot soulevé** : `venv/bin/python tools/test_moteurs.py --roues-soulevees`.
7. Pilotage : `venv/bin/python src/main.py`, puis **A** pour armer.
8. Démarrage automatique : `sudo systemctl enable --now esieabot` (ou `esieabot-web`).

## Commandes de la manette
| Commande | Action |
|---|---|
| **A** | Armer (joysticks au centre). LED bleue = armé |
| **B** | Stop et désarmement |
| **START** | Arrêt d'urgence verrouillé (alimentation moteur coupée) |
| **X** / **Y** | Profil LENT (55 %) / NORMAL (75 %) |
| **SELECT** | Mode MANUEL ↔ DUAL |
| Joystick gauche | Avancer/reculer + tourner |
| Croix | Déplacements lents de secours (45 %) |

## Pilotage web
`venv/bin/python src/web.py` puis ouvrir `http://pizero2w.local:8080` sur un appareil du même Wi-Fi. Le code d'accès à 4 chiffres s'affiche sur l'OLED. Plus de consigne depuis 0,5 s → moteurs à 0 ; plus de contact depuis 2 s → désarmé.

## Sécurités
- Démarrage toujours **désarmé** ; armement refusé si un joystick est poussé.
- Dongle débranché, défaut DRV8411 ou fin du programme → moteurs à 0.
- Même après un plantage brutal (`kill -9`), systemd force GPIO 17/22/23/25 à 0 (`ExecStopPost`).
- `pwm_minimum = 0,40` : mesuré, en dessous de 30 % une roue ne démarre pas.

## Tests
```bash
python3 -m unittest discover -s tests -v
```
Sans matériel. Sous Windows, les tests de la manette (qui utilisent `select()` sur un tube) sont ignorés.

## Avertissement
Projet personnel, non affilié à l'ESIEA. Faire les premiers essais **roues dans le vide**.
