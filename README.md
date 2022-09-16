# gax25-utils

python-based ham-radio / ax25 utilities based on the
[gensio](https://github.com/cminyard/gensio) ax25 stack.

Currently enough functionality is provided to host a Winlink RMS
gateway, and connect to it (and others) via `pat`
telnet sessions.

## Install `gensio` python bindings

```
python3 -m venv ./.venv
. .venv/bin/activate
pip install -r requirements.txt
```

## `gaxlisten.py`

a simple ax25-to-program proxy, useful for passing off to BBS or
gateway software.

### [`rmsgw`](https://github.com/nwdigitalradio/rmsgw) Winlink Gateway

```
python3 gaxlisten.py -l KF7HVM-5 -k tcp,localhost,8011 /usr/local/bin/rmsgw -l debug -P radio2 %U
```

compat note: traditionally, `-P` would have referred to an ax25 port name, but
it _really_ only points to a channel name in `rmsgw` `channels.xml` file.

eventually, it should be possible to build rmsgw without linux ax25 libraries.

## `gaxproxy.py`

Expose an ax25 client connection via a telnet listener.

```
python3 gaxproxy.py --mycall KF7HVM -k tcp,localhost,8010 --listen tcp,localhost,8772
```

In pat, connect via telnet to `whoever:KF7HVM-5@localhost:8772`.

The "password" is taken as the gateway to connect to!
