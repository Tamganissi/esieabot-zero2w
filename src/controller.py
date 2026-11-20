"""controller.py — Lecture de la manette ESIEA (dongle USB 2,4 GHz) via l'interface joystick Linux.

On utilise /dev/input/jsN, exactement comme les programmes officiels (linux/joystick.h)
et jstest : la numérotation des axes et boutons est donc la même que dans la doc ESIEAbot.
Format d'un événement (struct js_event) : uint32 temps_ms, int16 valeur, uint8 type, uint8 numéro.
"""
import errno
import glob
import os
import select
import struct

JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
FORMAT = "IhBB"
TAILLE = struct.calcsize(FORMAT)
AXE_MAX = 32767.0


class ManettePerdue(Exception):
    """Le dongle a été débranché ou le périphérique n'est plus lisible."""


def trouver_peripherique(chemin="auto"):
    if chemin and chemin != "auto":
        return chemin if os.path.exists(chemin) else None
    candidats = sorted(glob.glob("/dev/input/js*"))
    return candidats[0] if candidats else None


class Manette:
    def __init__(self, chemin, fd=None):
        self.chemin = chemin
        self.fd = fd if fd is not None else os.open(chemin, os.O_RDONLY | os.O_NONBLOCK)
        self.axes = {}      # numéro -> valeur normalisée [-1, 1]
        self.boutons = {}   # numéro -> 0/1
        self.nom = self._lire_nom()

    def _lire_nom(self):
        try:
            import fcntl
            buf = bytearray(128)
            JSIOCGNAME = 0x80006A13 + (128 << 16)  # _IOC(_IOC_READ, 'j', 0x13, 128)
            fcntl.ioctl(self.fd, JSIOCGNAME, buf)
            return buf.split(b"\0", 1)[0].decode(errors="replace")
        except Exception:
            return "inconnue"

    def lire(self, timeout=0.02):
        """Retourne la liste des événements (type, numero, valeur_brute, init) reçus.
        Lève ManettePerdue si le périphérique disparaît."""
        evts = []
        try:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return evts
            while True:
                try:
                    data = os.read(self.fd, TAILLE * 32)
                except BlockingIOError:
                    break
                if not data:
                    raise ManettePerdue("fin de flux")
                for i in range(0, len(data) - TAILLE + 1, TAILLE):
                    _t, val, typ, num = struct.unpack(FORMAT, data[i:i + TAILLE])
                    init = bool(typ & JS_EVENT_INIT)
                    typ &= ~JS_EVENT_INIT
                    if typ == JS_EVENT_AXIS:
                        self.axes[num] = max(-1.0, min(1.0, val / AXE_MAX))
                    elif typ == JS_EVENT_BUTTON:
                        self.boutons[num] = 1 if val else 0
                    evts.append((typ, num, val, init))
                if len(data) < TAILLE * 32:
                    break
        except OSError as e:
            if e.errno in (errno.ENODEV, errno.EIO, errno.EBADF):
                raise ManettePerdue(str(e))
            raise
        return evts

    def axe(self, numero):
        return self.axes.get(numero, 0.0)

    def fermer(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
