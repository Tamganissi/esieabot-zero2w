# Connecter un Raspberry Pi Zero 2 W à Windows 11 (USB + Wi-Fi)

Méthode testée le 18/11/2026 : Windows 11, Raspberry Pi OS Lite 64 bits (Trixie, 2026-10-06), Raspberry Pi Imager 2.0.12.

## Le principe
```
PC Windows ── Wi-Fi ───────────────────────── Pi (wlan0)   → ssh pi-wifi
     └── câble micro-USB DONNÉES, port « USB » du centre
           ├─ CDC-NCM : réseau 10.55.0.0/24, Pi = 10.55.0.1 → ssh pizero2w
           └─ CDC-ACM : port COMx 115200 bauds (console de secours)
```
- **NCM** plutôt que RNDIS : pilote natif Windows 11 (`usbncm.inf`), liaison automatique.
- Le lien USB n'annonce **ni passerelle ni DNS** : l'Internet du PC reste sur son Wi-Fi.

## 1. Clé SSH (PowerShell)
```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\id_ed25519
```

## 2. Écrire la carte
Raspberry Pi Imager → **Raspberry Pi Zero 2 W** → **Raspberry Pi OS Lite (64-bit)** → la microSD.
Si Windows propose de formater un disque après l'écriture : **Annuler**.

## 3. Configuration du premier démarrage
Si la personnalisation d'Imager n'est pas appliquée (`user-data` resté en modèle commenté), l'écrire avec :
```powershell
pwsh -File .\setup\windows\03_ecrire_cloudinit.ps1 -Boot E:\ -Ssid MonWifi -User pi
```
(mots de passe saisis dans une fenêtre masquée ; seul le hash du mot de passe du compte est écrit ; SSH par clé uniquement).

## 4. Gadget USB sur la partition `bootfs`
- `config.txt`, section `[all]` : `dtoverlay=dwc2,dr_mode=peripheral` (ou `otg` pour pouvoir aussi brancher un dongle) et `enable_uart=1`.
- Copier `setup/pi/` dans `bootfs/pizero2w/`. Le `runcmd` de cloud-init lance `install-gadget.sh` au premier démarrage, qui :
  - installe `pizero2w-gadget.sh` + service (gadget composite NCM + ACM via configfs, classe IAD obligatoire pour Windows) ;
  - ajoute la règle udev qui fait gérer `usb0` par NetworkManager (**sans elle, `usb0` reste DOWN**) ;
  - configure `usb0` en 10.55.0.1/24 avec DHCP sans passerelle ni DNS.
- Fichiers en fins de ligne **LF** uniquement ; `cmdline.txt` sur **une seule ligne**.

## 5. Premier démarrage
Câble **de données** PC ↔ port **« USB »** (centre), sans hub. 2 à 5 minutes. Windows doit afficher **UsbNcm Host Device** et un **port COM**. `setup/windows/04_detecter_pi.ps1` surveille l'arrivée du Pi.

## 6. Raccourcis SSH — `~\.ssh\config`
```
Host pizero2w pi-usb
    HostName 10.55.0.1
    User pi
    IdentityFile ~/.ssh/id_ed25519
    HostKeyAlias pizero2w

Host pi-wifi
    HostName pizero2w.local
    User pi
    IdentityFile ~/.ssh/id_ed25519
    HostKeyAlias pizero2w
```

## Dépannage
| Symptôme | Cause probable |
|---|---|
| Windows ne voit rien | Câble « charge seule », port « PWR IN », pas de `dtoverlay=dwc2` |
| « BCM2710 Boot » | Pas de carte démarrable |
| `VID_0000&PID_0002` | Câble ou alimentation |
| UsbNcm présent, pas de ping | `usb0` « unmanaged » → règle udev `86-pizero2w-usb0-managed.rules` |
| Dongle USB non reconnu | Port en `peripheral` → `sudo tools/usb_mode.sh otg --reboot` (SSH par Wi-Fi ensuite) |
| `pizero2w.local` ne répond pas mais l'IP oui | Le nom se résout en IPv6, bloqué par certains partages de connexion → dans `/etc/avahi/avahi-daemon.conf` : `use-ipv6=no` et `publish-aaaa-on-ipv4=no` |
| Instabilité | `vcgencmd get_throttled` doit renvoyer `0x0` |
