# systemd examples

unit files for working with various modems in conjunction with this package

1. Copy to $HOME/.config/systemd/user
2. `systemctl --user daemon-reload`

## Hybrid Gateway

  * Add `/opt/direwolf.conf`
  * install VARA FM at `/opt/wine-winlink`
  * `/usr/bin/env python3 -m pip install --user -r requirements.txt`

### Enable the appropriate units:

```
systemctl --user enable direwolf
systemctl --user enable diregate@KF7HVM-12
systemctl --user enable varafm
systemctl --user enable varagate@KF7HVM-12
```
