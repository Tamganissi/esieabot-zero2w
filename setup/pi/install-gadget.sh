#!/bin/bash
# install-gadget.sh — installe le gadget USB et la configuration réseau usb0 (exécuté une seule fois, en root)
# Source : /boot/firmware/pizero2w/   Journal : /var/log/pizero2w-install.log
# Réseau usb0 (NetworkManager) :
#   - 10.55.0.1/24 ; si dnsmasq est disponible -> mode "shared" : DHCP pour Windows (10.55.0.x)
#     SANS passerelle ni DNS annoncés (l'Internet du PC reste sur son Wi-Fi)
#   - 169.254.55.1/16 en plus : joignable même si Windows n'a qu'une adresse APIPA (pas de DHCP)
#   - never-default : le Pi ne route jamais son trafic par l'USB
set -u
SRC=/boot/firmware/pizero2w
exec >>/var/log/pizero2w-install.log 2>&1
echo "=== install $(date -Is) ==="

install -m 0755 "$SRC/pizero2w-gadget.sh"      /usr/local/sbin/pizero2w-gadget.sh
install -m 0644 "$SRC/pizero2w-gadget.service" /etc/systemd/system/pizero2w-gadget.service

# NetworkManager ignore les gadgets USB par défaut (/usr/lib/udev/rules.d/85-nm-unmanaged.rules,
# DEVTYPE==gadget -> NM_UNMANAGED=1). Constaté le 18/11/2026 : usb0 restait "unmanaged" et DOWN.
cat > /etc/udev/rules.d/86-pizero2w-usb0-managed.rules <<'EOF'
SUBSYSTEM=="net", ACTION=="add|change|move", ENV{DEVTYPE}=="gadget", ENV{INTERFACE}=="usb0", ENV{NM_UNMANAGED}="0"
EOF
udevadm control --reload-rules || true

CON=/etc/NetworkManager/system-connections/usb0-gadget.nmconnection
if command -v dnsmasq >/dev/null 2>&1; then METHOD=shared; else METHOD=manual; fi
cat > "$CON" <<EOF
[connection]
id=usb0-gadget
type=ethernet
interface-name=usb0
autoconnect=true
autoconnect-priority=10

[ethernet]

[ipv4]
method=$METHOD
address1=10.55.0.1/24
address2=169.254.55.1/16
never-default=true
ignore-auto-dns=true

[ipv6]
method=link-local
EOF
chmod 600 "$CON"
if [ "$METHOD" = shared ]; then
  mkdir -p /etc/NetworkManager/dnsmasq-shared.d
  cat > /etc/NetworkManager/dnsmasq-shared.d/usb0-nogateway.conf <<'EOF'
# Lien USB : DHCP uniquement, ni passerelle ni DNS annoncés à Windows
dhcp-option=option:router
dhcp-option=option:dns-server
EOF
fi
echo "usb0: méthode IPv4 = $METHOD"

systemctl daemon-reload
systemctl enable pizero2w-gadget.service
systemctl start pizero2w-gadget.service || echo "start gadget: échec (voir journalctl -u pizero2w-gadget)"
nmcli connection reload || true
echo "=== fin install ==="
