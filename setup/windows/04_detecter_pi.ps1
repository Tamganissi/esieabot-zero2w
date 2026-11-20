<#
.SYNOPSIS
  Surveille l'apparition du Raspberry Pi (lecture seule) et journalise chaque changement.
.DESCRIPTION
  Toutes les 5 s, pendant -Minutes minutes, contrôle :
   - USB : VID_1D6B&PID_0104 (gadget pizero2w), VID_0A5C&PID_2764 (BCM2710 Boot = carte non démarrable)
   - Carte réseau UsbNcm et son adresse IPv4
   - Port COM du gadget (usbser)
   - mDNS : résolution de pizero2w.local et port SSH 22 (Wi-Fi ou USB)
  S'arrête dès que le gadget USB ET SSH sont joignables, ou à l'échéance.
.USAGE
  pwsh -File .\scripts\04_detecter_pi.ps1 [-Minutes 12] [-Log ..\tests\detection.log]
#>
param([int]$Minutes = 12, [string]$Log = "$(Split-Path $PSScriptRoot -Parent)\tests\detection.log")
New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
function L($m) { $s = "$(Get-Date -Format HH:mm:ss)  $m"; Add-Content $Log $s -Encoding UTF8; $s }
function Test-Port($h, $p) { try { $c = New-Object Net.Sockets.TcpClient; $ok = $c.ConnectAsync($h, $p).Wait(1500) -and $c.Connected; $c.Close(); $ok } catch { $false } }
L "=== Début surveillance ($Minutes min) ==="
$last = @{}; $end = (Get-Date).AddMinutes($Minutes)
while ((Get-Date) -lt $end) {
  $st = [ordered]@{}
  $dev = Get-PnpDevice -PresentOnly -EA SilentlyContinue | ? InstanceId -match 'VID_1D6B&PID_0104|VID_0A5C&PID_2764|VID_0000&PID_0002'
  $st.USB = if ($dev) { ($dev | % { "$($_.Status) $($_.Class) $($_.FriendlyName) [$($_.InstanceId -replace '\\[^\\]+$','')]" }) -join ' | ' } else { 'rien' }
  $ncm = Get-NetAdapter -EA SilentlyContinue | ? InterfaceDescription -match 'NCM|UsbNcm'
  $st.NCM = if ($ncm) { $ip = (Get-NetIPAddress -InterfaceIndex $ncm.ifIndex -AddressFamily IPv4 -EA SilentlyContinue).IPAddress; "$($ncm.Name) $($ncm.Status) IPv4=$($ip -join ',')" } else { 'absente' }
  $st.COM = (Get-CimInstance Win32_SerialPort -EA SilentlyContinue | ? PNPDeviceID -match 'VID_1D6B&PID_0104' | % DeviceID) -join ','
  $mdns = (Resolve-DnsName pizero2w.local -Type A -QuickTimeout -EA SilentlyContinue | ? IPAddress | % IPAddress) -join ','
  $st.mDNS = if ($mdns) { $mdns } else { 'non résolu' }
  $st.SSH_usb  = Test-Port '10.55.0.1' 22
  $st.SSH_ll   = Test-Port '169.254.55.1' 22
  $st.SSH_mdns = if ($mdns) { Test-Port ($mdns -split ',')[0] 22 } else { $false }
  foreach ($k in $st.Keys) { if ("$($last[$k])" -ne "$($st[$k])") { L "$k : $($st[$k])"; $last[$k] = $st[$k] } }
  if ($dev -match 'PID_0104' -and ($st.SSH_usb -or $st.SSH_ll) -and $st.SSH_mdns) { L '=== Pi détecté : gadget USB + SSH USB + SSH Wi-Fi joignables ==='; break }
  Start-Sleep -Seconds 5
}
L "=== Fin surveillance ==="
