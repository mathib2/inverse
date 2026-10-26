# Getting into INVERSE

## The app, for anyone on the team

The live crew UI is reachable two ways. Both end on the same sign-in page; the user and password come from the project owner,
never from this repository.

| way | who | address |
|---|---|---|
| **public link** | anyone with a browser, phone included; nothing to install | the current `https://….trycloudflare.com` link: the owner shares it, and signed-in people see it under **Share with your team** in the sidebar |
| **tailnet** | people already on the owner's Tailscale network | port 8501 of the workstation's Tailscale address |

The public link is a Cloudflare quick tunnel (`scripts/public_link.py`, run with `~/.local/bin/inverse-public start|stop|status|url|log`
on the workstation). It costs nothing and needs no account, and its address changes whenever the tunnel restarts; the new address
is sent to the owner's phone and shown in the sidebar.

The sign-in page is the only gate, so it is hardened for the open internet: five wrong tries from one address lock that address
out for fifteen minutes, thirty wrong tries from anywhere slow every try, and a device stays signed in for seven days through a
signed cookie that **Sign out** revokes. Change the password with `scripts/admin/set_password.py` (it writes only a salted hash to `.env`)
and `deploy-live`; a new password signs every device out.

## A link that never changes (optional, once, by the owner)

Tailscale Funnel gives the workstation a permanent public address, `https://<machine>.<tailnet>.ts.net`, with no third party in
between. The public-link service (`scripts/public_link.py`) tries Funnel first, at start and every 15 minutes while it runs the
quick tunnel, and switches to it by itself, so the owner only has to allow it:

1. Open the approval link the service keeps in `state/public_url.json` (`funnel_enable`, also in `inverse-public log`), signed in
   to Tailscale as the tailnet's owner, and approve. It turns on HTTPS certificates and the `funnel` attribute for this machine.
2. Only if the log then says this user may not change Tailscale's serve settings: on the workstation, once,
   `sudo tailscale set --operator=$USER`.

Within 15 minutes the sidebar and the phone show the permanent address, and the quick tunnel stops.

## The code

The repository is private: the owner adds each person as a collaborator on GitHub. The working branch is `m4-sindyc`;
`README.md`, `docs/CREW.md` and `docs/BENCH.md` are the place to start.
