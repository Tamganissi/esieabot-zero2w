<#
.SYNOPSIS
  Écrit la configuration de premier démarrage (cloud-init) sur la partition bootfs de la microSD.
.DESCRIPTION
  - Ouvre une fenêtre où l'utilisateur saisit (champs masqués) le mot de passe du compte et celui du Wi-Fi.
  - Le mot de passe du compte est haché localement (SHA-512 crypt, openssl de Git) : seul le hash est écrit.
  - Le mot de passe Wi-Fi est écrit dans network-config (comme le fait Raspberry Pi Imager).
  - Aucun secret n'est affiché ni journalisé.
  - Les originaux de user-data / network-config doivent être sauvegardés AVANT (fait dans sauvegardes\).
.USAGE
  pwsh -File .\scripts\03_ecrire_cloudinit.ps1 -Boot D:\ -Ssid MonWifi [-User pi] [-Hostname pizero2w]
#>
param(
  [Parameter(Mandatory)][string]$Boot,
  [string]$User = 'pi',
  [string]$Hostname = 'pizero2w',
  [Parameter(Mandatory)][string]$Ssid,
  [string]$PubKeyFile = "$HOME\.ssh\id_ed25519.pub",
  [string]$OpenSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path (Join-Path $Boot 'config.txt'))) { throw "$Boot n'est pas une partition bootfs" }
$pub = (Get-Content $PubKeyFile -Raw).Trim()

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$f = New-Object Windows.Forms.Form -Property @{ Text = "Raspberry Pi $Hostname — mots de passe"; Width = 460; Height = 300; StartPosition = 'CenterScreen'; TopMost = $true; FormBorderStyle = 'FixedDialog' }
$y = 15
function Add-Field($label) {
  $l = New-Object Windows.Forms.Label -Property @{ Text = $label; Left = 15; Top = $script:y; Width = 420 }
  $t = New-Object Windows.Forms.TextBox -Property @{ Left = 15; Top = $script:y + 20; Width = 410; UseSystemPasswordChar = $true }
  $f.Controls.AddRange(@($l, $t)); $script:y += 50; return $t
}
$p1 = Add-Field "Mot de passe du compte Linux '$User' (console série, sudo)"
$p2 = Add-Field "Confirmer le mot de passe du compte"
$pw = Add-Field "Mot de passe du Wi-Fi '$Ssid'"
$ok = New-Object Windows.Forms.Button -Property @{ Text = 'Valider'; Left = 255; Top = $y + 5; Width = 80; DialogResult = 'OK' }
$ca = New-Object Windows.Forms.Button -Property @{ Text = 'Annuler'; Left = 345; Top = $y + 5; Width = 80; DialogResult = 'Cancel' }
$f.Controls.AddRange(@($ok, $ca)); $f.AcceptButton = $ok; $f.CancelButton = $ca

do {
  if ($f.ShowDialog() -ne 'OK') { throw 'Annulé par l''utilisateur : rien n''a été écrit.' }
  $err = if ($p1.Text.Length -lt 8) { 'Mot de passe du compte : 8 caractères minimum.' }
         elseif ($p1.Text -ne $p2.Text) { 'Les deux mots de passe du compte diffèrent.' }
         elseif ($pw.Text.Length -lt 8 -or $pw.Text.Length -gt 63) { 'Mot de passe Wi-Fi WPA2 : 8 à 63 caractères.' }
  if ($err) { [Windows.Forms.MessageBox]::Show($err) | Out-Null }
} while ($err)

$hash = ($p1.Text | & $OpenSsl passwd -6 -stdin).Trim()
if ($hash -notmatch '^\$6\$') { throw 'Échec du hachage' }
$wifi = $pw.Text -replace "'", "''"          # échappement YAML (chaîne entre apostrophes)
$p1.Text = ''; $p2.Text = ''; $pw.Text = ''; $f.Dispose()

$userData = @"
#cloud-config
# Généré par 03_ecrire_cloudinit.ps1 — premier démarrage de $Hostname
hostname: $Hostname
manage_etc_hosts: true
timezone: Europe/Paris
keyboard:
  model: pc105
  layout: fr
users:
- name: $User
  groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
  shell: /bin/bash
  lock_passwd: false
  passwd: $hash
  sudo: ALL=(ALL) NOPASSWD:ALL
  ssh_authorized_keys:
  - $pub
enable_ssh: true
ssh_pwauth: false
disable_root: true
runcmd:
- [systemctl, enable, --now, ssh]
- [bash, /boot/firmware/pizero2w/install-gadget.sh]
"@

$netCfg = @"
# Généré par 03_ecrire_cloudinit.ps1
network:
  version: 2
  wifis:
    wlan0:
      dhcp4: true
      optional: true
      regulatory-domain: FR
      access-points:
        '$($Ssid -replace "'", "''")':
          password: '$wifi'
"@

$utf8 = New-Object Text.UTF8Encoding($false)   # UTF-8 sans BOM, fins de ligne LF
[IO.File]::WriteAllText((Join-Path $Boot 'user-data'),      ($userData -replace "`r`n", "`n") + "`n", $utf8)
[IO.File]::WriteAllText((Join-Path $Boot 'network-config'), ($netCfg  -replace "`r`n", "`n") + "`n", $utf8)
$wifi = $null; $hash = $null
'user-data et network-config écrits (secrets non affichés).'
