# gensio-modems

python-based ham-radio modem utilities (ax25, kiss, vara) built using
[gensio](https://github.com/cminyard/gensio).

Currently enough functionality is provided to host a Winlink RMS
gateway, and connect to it (and others) via `pat`
telnet sessions.

## Install `gensio-modems`

```
python3 -m venv ./.venv
. .venv/bin/activate
pip install gensio-modems
```

alternatively, if you don't want a virtualenv,

```
pip install --user gensio-modems
```

## `varagate.py`

RMS/Winlink capable gateway for VARA and VARA FM

```
python examples/varagate.py -l KF7HVM-10 --banner "gensio+vara experimental rms gateway" --gateway "rms,tcp,cms.winlink.org,8772"
```

## `listen.py`

a simple ax25-to-program proxy, useful for passing off to BBS or
gateway software.

### [`rmsgw`](https://github.com/nwdigitalradio/rmsgw) Winlink Gateway

```
python -m gensio_modems.listen -l KF7HVM-10 -k tcp,localhost,8011 /usr/local/bin/rmsgw -l debug -P radio2 %U
```

#### _as a service_

```
Description="Service for gensio rmsgw"
After=direwolf@dw1.service
BindsTo=direwolf@dw1.service

[Service]
RestartSec=5
Restart=always
User=rmsgw
ExecStart=/home/rmsgw/.gensio/bin/python -m gensio_modems.listen -l N7DEM-12 \
    /usr/local/bin/rmsgw -l debug -P dw1 %%U

[Install]
WantedBy=direwolf@dw1.service multi-user.target
```

compat note: traditionally, `-P` would have referred to an ax25 port name, but
it _really_ only points to a channel name in `rmsgw` `channels.xml` file.

eventually, it should be possible to build rmsgw without linux ax25 libraries.

## `proxy.py`

Expose an ax25 client connection via a telnet listener.

```
python -m gensio_modems.proxy --mycall KF7HVM-1 -k tcp,localhost,8010 --listen tcp,localhost,8772
```

In pat, connect via telnet to `pat:KF7HVM-10@localhost:8772`.

The "password" is taken as the gateway to connect to!
