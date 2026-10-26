# Keeping Nightshift reachable from the workstation

Nightshift (the Meterless Runtime) has no Linux build, so it runs on a Windows laptop and the workstation reaches it at `127.0.0.1:8088` through an SSH **reverse** tunnel opened *from the laptop*. Nightshift is INVERSE's primary provider; when the laptop sleeps or the tunnel drops, the crew keeps working on the workstation's Ollama (the sidebar shows **AI online · fallback**) and returns to Nightshift by itself.

## How it is set up (2026-10-26)

- **One lane for the crew.** Nightshift's fleet `inverse` has a single lane, `Nemotron-Mini-4B-Instruct-Q4_K_M.gguf` (the same file Ollama serves on the workstation, copied into Nightshift's models folder), 2 slots of 4096 tokens, fully on the laptop's GPU. Its route is `local-runtime/nemotron-mini-4b-instruct-q4-k-m`; the aliases `nemotron-mini` and `nemotron-mini:latest` reach it too. Measured: about 59 tokens a second end to end, a short JSON reply in under a second through the tunnel. The previous fleet (`jury-lite`, six lanes, more than the laptop's memory) is still defined and can be re-activated.
- **The Documents folder.** With Windows' Documents folder in OneDrive, Nightshift's engine froze at startup while creating its default workspace there, so its API never opened. The launcher sets `XDG_DOCUMENTS_DIR` to a local folder before starting Nightshift; the engine honours it.
- **The launcher** `%USERPROFILE%\nightshift-tunnel.ps1`, run at logon by the scheduled task **Nightshift tunnel**: starts Nightshift if it is not running (and restarts it if its API does not answer within two minutes), then keeps `ssh -N -R 127.0.0.1:8088:127.0.0.1:<Nightshift's port>` open forever. The tunnel key may open only `127.0.0.1:8088` on the workstation.
- **The workstation's `.env`** (in `~/inverse-live`; `~/inverse-dev` links to it): `MODEL_PROVIDER=nightshift`, `MODEL_BASE_URL=http://127.0.0.1:8088/v1`, `MODEL_API_KEY` = Nightshift's runtime key (the `proxy-token` file in `%LOCALAPPDATA%\ai.meterless.runtime`), `NEMOTRON_MODEL` and `LANE_FAST`, `LANE_DEEP`, `LANE_CRITIC` = the route above, `MODEL_FALLBACK_URL=http://127.0.0.1:11434/v1`, `MODEL_FALLBACK_MODEL=nemotron-mini:latest`. Tinker's sandbox (`~/inverse-lab`) has its own `.env` on Ollama, so its measurements stay comparable.
- **Stop it:** `Disable-ScheduledTask -TaskName "Nightshift tunnel"` and close Nightshift; the crew runs on the fallback.

The sections below are the original one-time setup (2026-10-24).

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
