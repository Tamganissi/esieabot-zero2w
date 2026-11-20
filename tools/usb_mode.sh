#!/bin/bash
# usb_mode.sh — Choisit le rôle du port USB de données ("USB", au centre) du Pi Zero 2 W.
#   otg     : automatique (câble PC -> gadget réseau/série ; adaptateur OTG -> hôte pour le dongle)
#   host    : hôte forcé (dongle de la manette). Le SSH se fait alors UNIQUEMENT par Wi-Fi (ssh pi-wifi).
#   gadget  : périphérique forcé (réseau USB + COM vers le PC). Le dongle ne peut PAS fonctionner.
# Sauvegarde de config.txt avant chaque modification. Prise en compte au prochain redémarrage.
# Usage : sudo ~/esieabot/tools/usb_mode.sh otg|host|gadget [--reboot]
set -euo pipefail
CFG=/boot/firmware/config.txt
case "${1:-}" in
  otg)    MODE=otg ;;
  host)   MODE=host ;;
  gadget) MODE=peripheral ;;
  *) echo "usage: $0 otg|host|gadget [--reboot]"; grep -n 'dtoverlay=dwc2' "$CFG"; exit 2 ;;
esac
[ "$(id -u)" = 0 ] || { echo "à lancer avec sudo"; exit 1; }
LIGNE=$(grep -n '^dtoverlay=dwc2,dr_mode=' "$CFG" | tail -n1 | cut -d: -f1)
[ -n "$LIGNE" ] || { echo "ligne dtoverlay=dwc2 de la section [all] introuvable"; exit 1; }
cp -a "$CFG" "$CFG.$(date +%Y%m%d_%H%M%S).bak"
sed -i "${LIGNE}s/^dtoverlay=dwc2,dr_mode=.*/dtoverlay=dwc2,dr_mode=${MODE}/" "$CFG"
echo "config.txt ligne $LIGNE : $(sed -n "${LIGNE}p" "$CFG")"
[ "${2:-}" = "--reboot" ] && { echo "redémarrage..."; systemctl reboot; } || echo "redémarrez pour appliquer : sudo reboot"
