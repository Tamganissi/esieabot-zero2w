"""power.py — Carte d'alimentation ESIEAbot (RP2040/RP2350, I2C 0x5A).

Protocole repris du code officiel esieabot-power-manager/power-cli.py (gitlab.esiea.fr),
réécrit avec smbus2 car pigpiod n'est pas disponible sous Debian 13.
Si la carte ne répond pas (robot alimenté uniquement par l'USB du PC), tout est ignoré proprement.
"""
import logging
import struct

log = logging.getLogger("power")

VMOT_VOLTAGE = 0x08
BATT_VOLTAGE = 0x01
BATT_SOC = 0x06
DISABLE_MOTORS = 0x0E
ENABLE_MOTORS = 0x0F
NEED_SWITCH_OFF = 0x14


class CarteAlim:
    def __init__(self, cfg):
        self.adr = int(cfg["carte_alimentation"]["adresse_i2c"])
        self.present = False
        try:
            from smbus2 import SMBus
            self.bus = SMBus(1)
            self.bus.read_i2c_block_data(self.adr, BATT_SOC, 1)
            self.present = True
            log.info("carte d'alimentation détectée en 0x%02X", self.adr)
        except Exception as e:
            log.warning("carte d'alimentation absente en 0x%02X (%s)", self.adr, e)

    def _float(self, reg):
        return struct.unpack("f", bytes(self.bus.read_i2c_block_data(self.adr, reg, 4)))[0]

    def vmot(self):
        return self._float(VMOT_VOLTAGE) if self.present else None

    def vbat(self):
        return self._float(BATT_VOLTAGE) if self.present else None

    def moteurs(self, actifs):
        if self.present:
            try:
                self.bus.write_byte(self.adr, ENABLE_MOTORS if actifs else DISABLE_MOTORS)
            except Exception as e:
                log.error("commande moteurs carte alim : %s", e)

    def demande_extinction(self):
        if not self.present:
            return False
        try:
            return self.bus.read_i2c_block_data(self.adr, NEED_SWITCH_OFF, 1)[0] == 1
        except Exception:
            return False
