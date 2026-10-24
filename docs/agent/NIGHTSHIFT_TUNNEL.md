# Keeping Nightshift reachable from the workstation

Nightshift (the Meterless Runtime) has no Linux build, so it runs on a Windows laptop and the workstation reaches it at `127.0.0.1:8088` through an SSH **reverse** tunnel opened *from the laptop*. When the laptop sleeps or the window closes, the AI goes offline for everyone (the UI shows **AI · Offline** and runs pause). Tonight (2026-10-24, 01:41 CDT) that stopped a live evaluation halfway.

## One-time setup on the laptop (PowerShell)

1. Make a key for the tunnel, no passphrase, and install it on the workstation (you will type the workstation password once):

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_tunnel -N '""'
type $env:USERPROFILE\.ssh\id_ed25519_tunnel.pub | ssh <user>@<workstation> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

2. Save this as `C:\Users\<you>\nightshift-tunnel.ps1`. It reconnects on its own after sleep, drops a dead forward instead of holding the port, and never asks for a password:

```powershell
# Reverse tunnel for Meterless Nightshift: workstation:8088 -> this laptop:8088. Reconnects forever.
$target = "<user>@<workstation>"
$key = "$env:USERPROFILE\.ssh\id_ed25519_tunnel"
while ($true) {
  ssh -i $key -o BatchMode=yes -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes `
      -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new `
      -N -R 127.0.0.1:8088:127.0.0.1:8088 $target
  "$(Get-Date -Format s) tunnel closed (exit $LASTEXITCODE), retrying in 10 s" | Tee-Object -FilePath "$env:USERPROFILE\nightshift-tunnel.log" -Append
  Start-Sleep -Seconds 10
}
```

3. Run it at logon without a window (Task Scheduler, once):

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $env:USERPROFILE\nightshift-tunnel.ps1"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "Nightshift tunnel" -Action $action -Trigger $trigger -Description "Reverse SSH tunnel for Meterless Nightshift" -RunLevel Limited
Start-ScheduledTask -TaskName "Nightshift tunnel"
```

4. Keep the laptop awake while the demo or an evaluation runs: Settings → System → Power → *Never* sleep on power, or `powercfg /change standby-timeout-ac 0`.

## On the workstation (needs sudo, once)

Without keepalives a dead tunnel can hold port 8088 for a long time, so the next connection fails with *remote port forwarding failed*:

```bash
printf "MaxStartups 30:30:100\nClientAliveInterval 20\nClientAliveCountMax 3\n" | sudo tee /etc/ssh/sshd_config.d/02-inverse.conf
sudo sshd -t && sudo systemctl reload ssh
```

## How to tell what is wrong

| Symptom | Meaning |
|---|---|
| `curl -s http://127.0.0.1:8088/healthz` on the workstation: connection refused | no tunnel; start the script on the laptop |
| `/healthz` ok but `/v1/models` is 401 | the Runtime token in `.env` is not this Nightshift's; store the new one with `~/.local/bin/set-nightshift-token` |
| `remote port forwarding failed for listen port 8088` on the laptop | a dead forward still holds the port; the keepalive drop-in above fixes it, or `pkill -f 'sshd: .*<user>'` the stale session |
| Nightshift's Console shows 127.0.0.1:8088 but `/healthz` fails on the laptop itself | the Runtime did not start (port conflict); restart Nightshift |

The UI never prints the address or user name on screen (set `INVERSE_SHOW_SSH_TARGET=1` to allow it on a private screen).
