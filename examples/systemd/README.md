# systemd examples

unit files for working with various modems in conjunction with this package

1. Copy to $HOME/.config/systemd/user
2. `systemctl --user daemon-reload`

## Hybrid Gateway

  * Add `/opt/direwolf.conf`
  * install VARA FM at `/opt/wine-winlink`
  * `/usr/bin/python3 -m pip install --user -r requirements.txt`

### Enable the appropriate units:

```
systemctl --user enable direwolf
systemctl --user enable diregate@KF7HVM-12
systemctl --user enable varafm
systemctl --user enable varagate@KF7HVM-12
```

## Winlink Client

```
systemctl --user start winlink
```

(this will stop the gateway, as only one app can connect to VARA).

_After winlink exits, `systemctl --user restart varafm` to bring the
gateway back up._
