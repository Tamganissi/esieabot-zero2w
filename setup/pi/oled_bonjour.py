#!/usr/bin/env python3
"""oled_bonjour.py — Affiche un texte sur un écran OLED SSD1306 I2C (adresse 0x3C, bus 1).

Dépendances (paquets Debian) : python3-smbus2, python3-pil
Usage : python3 oled_bonjour.py [texte] [--hauteur 64|32]
"""
import sys
from smbus2 import SMBus, i2c_msg
from PIL import Image, ImageDraw, ImageFont

ADDR, BUS, W = 0x3C, 1, 128
args = [a for a in sys.argv[1:] if not a.startswith("--")]
H = 32 if "--hauteur" in sys.argv and sys.argv[sys.argv.index("--hauteur") + 1] == "32" else 64
if args and args[-1] in ("32", "64"):
    args = args[:-1]
TEXTE = " ".join(args) or "Bonjour"


def cmd(bus, *c):
    bus.i2c_rdwr(i2c_msg.write(ADDR, [0x00, *c]))   # 0x00 = octet de contrôle "commandes"


def init(bus):
    cmd(bus, 0xAE)                                  # écran éteint
    cmd(bus, 0xD5, 0x80)                            # horloge
    cmd(bus, 0xA8, H - 1)                           # multiplexage = hauteur
    cmd(bus, 0xD3, 0x00)                            # décalage vertical
    cmd(bus, 0x40)                                  # ligne de départ 0
    cmd(bus, 0x8D, 0x14)                            # pompe de charge interne ON
    cmd(bus, 0x20, 0x00)                            # adressage horizontal
    cmd(bus, 0xA1, 0xC8)                            # orientation (miroir H + V)
    cmd(bus, 0xDA, 0x12 if H == 64 else 0x02)       # broches COM
    cmd(bus, 0x81, 0xCF)                            # contraste
    cmd(bus, 0xD9, 0xF1, 0xDB, 0x40)                # pré-charge, VCOMH
    cmd(bus, 0xA4, 0xA6)                            # suit la RAM, affichage normal
    cmd(bus, 0xAF)                                  # écran allumé


def afficher(bus, img):
    cmd(bus, 0x21, 0, W - 1, 0x22, 0, H // 8 - 1)   # fenêtre = tout l'écran
    px = img.load()
    data = []
    for page in range(H // 8):
        for x in range(W):
            b = 0
            for bit in range(8):
                if px[x, page * 8 + bit]:
                    b |= 1 << bit
            data.append(b)
    for i in range(0, len(data), 16):               # paquets de 16 octets (0x40 = "données")
        bus.i2c_rdwr(i2c_msg.write(ADDR, [0x40, *data[i:i + 16]]))


img = Image.new("1", (W, H), 0)
d = ImageDraw.Draw(img)
taille = 26 if H == 64 else 20
try:
    font = ImageFont.load_default(size=taille)
except TypeError:
    font = ImageFont.load_default()
x0, y0, x1, y1 = d.textbbox((0, 0), TEXTE, font=font)
d.text(((W - (x1 - x0)) // 2 - x0, (H - (y1 - y0)) // 2 - y0), TEXTE, font=font, fill=1)
d.rectangle((0, 0, W - 1, H - 1), outline=1)        # cadre : permet de vérifier la taille réelle de l'écran

with SMBus(BUS) as bus:
    init(bus)
    afficher(bus, img)
    etat = bus.read_byte(ADDR)
print(f"OK : '{TEXTE}' envoyé à 0x{ADDR:02X} ({W}x{H}), octet d'état après envoi = 0x{etat:02X}")
