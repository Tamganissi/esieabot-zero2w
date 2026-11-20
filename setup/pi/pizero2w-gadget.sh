#!/bin/bash
# pizero2w-gadget.sh — Gadget USB composite pour Raspberry Pi Zero 2 W
#   Fonction 1 : CDC-NCM  -> carte réseau "UsbNcm" native sous Windows 11 (usbncm.inf)
#   Fonction 2 : CDC-ACM  -> port COMx natif sous Windows (usbser.inf), console de secours
# Usage : pizero2w-gadget.sh start|stop     (appelé par pizero2w-gadget.service)
# Prérequis : dtoverlay=dwc2,dr_mode=peripheral dans /boot/firmware/config.txt
# Réversible : sudo systemctl disable --now pizero2w-gadget.service
set -euo pipefail
G=/sys/kernel/config/usb_gadget/pizero2w

start() {
  modprobe libcomposite
  mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
  [ -d "$G" ] && { echo "gadget déjà présent"; exit 0; }
  mkdir -p "$G"; cd "$G"
  echo 0x1d6b > idVendor      # Linux Foundation
  echo 0x0104 > idProduct     # Multifunction Composite Gadget
  echo 0x0100 > bcdDevice
  echo 0x0200 > bcdUSB
  # Classe "Miscellaneous / IAD" : obligatoire pour qu'un composite NCM+ACM soit découpé correctement par Windows
  echo 0xEF > bDeviceClass; echo 0x02 > bDeviceSubClass; echo 0x01 > bDeviceProtocol

  SERIAL=$(awk '/^Serial/{print $3}' /proc/cpuinfo); SERIAL=${SERIAL:-0000000000000000}
  mkdir -p strings/0x409
  echo "$SERIAL"           > strings/0x409/serialnumber
  echo "Raspberry Pi"      > strings/0x409/manufacturer
  echo "pizero2w USB (NCM+Serie)" > strings/0x409/product

  mkdir -p configs/c.1/strings/0x409
  echo "NCM + ACM" > configs/c.1/strings/0x409/configuration
  echo 250 > configs/c.1/MaxPower

  # Adresses MAC fixes (administrées localement, dérivées du n° de série) -> Windows garde la même carte réseau
  S=${SERIAL: -6}
  mkdir -p functions/ncm.usb0
  echo "02:22:${S:0:2}:${S:2:2}:${S:4:2}:01" > functions/ncm.usb0/host_addr
  echo "02:22:${S:0:2}:${S:2:2}:${S:4:2}:02" > functions/ncm.usb0/dev_addr
  mkdir -p functions/acm.usb0

  ln -s functions/ncm.usb0 configs/c.1/
  ln -s functions/acm.usb0 configs/c.1/

  UDC=$(ls /sys/class/udc | head -n1)
  [ -n "$UDC" ] || { echo "ERREUR: aucun contrôleur UDC (dtoverlay=dwc2 absent ?)" >&2; exit 1; }
  echo "$UDC" > UDC
  echo "gadget lié à $UDC"
  # Console de secours sur le port série USB
  systemctl start --no-block serial-getty@ttyGS0.service || true
}

stop() {
  [ -d "$G" ] || exit 0
  cd "$G"
  echo "" > UDC 2>/dev/null || true
  rm -f configs/c.1/ncm.usb0 configs/c.1/acm.usb0
  rmdir configs/c.1/strings/0x409 configs/c.1 functions/ncm.usb0 functions/acm.usb0 strings/0x409 2>/dev/null || true
  cd /; rmdir "$G" 2>/dev/null || true
}

case "${1:-}" in start) start ;; stop) stop ;; *) echo "usage: $0 start|stop"; exit 2 ;; esac
