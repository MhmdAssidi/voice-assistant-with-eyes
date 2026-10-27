# Opens the Windows Firewall ports the phone needs to reach this laptop (Student B, B1).
# Run ONCE per laptop in an ADMINISTRATOR PowerShell, from the repo root:
#   powershell -ExecutionPolicy Bypass -File infra\mediamtx\open-firewall.ps1
#
# Rules only accept traffic from the local network (LocalSubnet), on any network profile,
# because a new Wi-Fi or phone hotspot is often marked "Public" by Windows.
# Safe to run again: old rules with the same names are replaced.

#Requires -RunAsAdministrator

$rules = @(
    @{ Name = "VA Eyes - WebRTC signaling (WHIP/WHEP)"; Protocol = "TCP"; Port = 8889 },
    @{ Name = "VA Eyes - WebRTC media";                 Protocol = "UDP"; Port = 8189 },
    @{ Name = "VA Eyes - HLS fallback";                 Protocol = "TCP"; Port = 8888 },
    @{ Name = "VA Eyes - API (phone asks questions)";   Protocol = "TCP"; Port = 8000 }
)

foreach ($r in $rules) {
    Remove-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Action Allow `
        -Protocol $r.Protocol -LocalPort $r.Port -RemoteAddress LocalSubnet -Profile Any | Out-Null
    Write-Host ("Opened {0} {1}  ({2})" -f $r.Protocol, $r.Port, $r.Name)
}
