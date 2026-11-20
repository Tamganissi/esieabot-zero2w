#!/bin/bash
# install.sh — Installe esieabot-zero2w sur un Raspberry Pi (Raspberry Pi OS Trixie, arm64).
# À lancer depuis le dossier du projet, SANS sudo : ./install.sh
# Les services systemd sont installés mais PAS activés (à faire après les essais).
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
[ "$(id -u)" != 0 ] || { echo "Lancer sans sudo (le script l'utilise quand il faut)."; exit 1; }

echo "== Paquets système"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev i2c-tools joystick usbutils swig liblgpio-dev

echo "== Environnement Python"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "== Groupes (gpio, i2c, input)"
sudo usermod -aG gpio,i2c,input "$USER"

echo "== Services systemd (dossier : $DIR, utilisateur : $USER)"
for s in systemd/*.service; do
  sed -e "s#__HOME__/esieabot#$DIR#g" -e "s#__USER__#$USER#g" "$s" | sudo tee "/etc/systemd/system/$(basename "$s")" >/dev/null
done
sudo systemctl daemon-reload
mkdir -p logs

echo "== Terminé."
echo "Tests :        venv/bin/python -m unittest discover -s tests"
echo "Simulation :   venv/bin/python src/main.py --simulation"
echo "Auto-start :   sudo systemctl enable --now esieabot   (ou esieabot-web)"
