"""AX.25 / KISS modem implementation."""
import argparse
import logging

import gensio

from gensio_modems.gutils import ListenerEvent, PipeEvent, OSFUNCS
from gensio_modems.rmsgw import RMSGatewayLogin


logger = logging.getLogger("ax25")


def ax25_addr(io, control):
    addr = io.control(0, True, control, b"")
    gensio_name, _, addr_str = addr.partition(":")
    addrs = addr_str.split(",")
    return addrs[1] if len(addrs) > 1 else addrs[0]


def ax25_remote_addr(io):
    return ax25_addr(io, control=gensio.GENSIO_CONTROL_RADDR)


def ax25_local_addr(io):
    return ax25_addr(io, control=gensio.GENSIO_CONTROL_LADDR)


def ax25_command_substitution(io, command):
    remote_addr = ax25_remote_addr(io)
    remote_callsign = remote_addr.partition("-")[0]
    # from https://manpages.ubuntu.com/manpages/jammy/man5/ax25d.conf.5.html
    replmap = {
        "%d": "gax25",
        "%U": remote_callsign.upper(),
        "%u": remote_callsign.lower(),
        "%S": remote_addr.upper(),
        "%s": remote_addr.lower(),
        "%P": "%%",
        "%p": "%%",
        "%R": "%%",
        "%r": "%%",
        "%%": "%%",
    }
    for find, repl in replmap.items():
        if find in command:
            command = command.replace(find, repl)
    return command


def spawn_for(ioev, gensio_str):
    sh_cmd = ax25_command_substitution(ioev.io, gensio_str)
    logger.info("spawn: {}".format(sh_cmd))
    return gensio.gensio(OSFUNCS, sh_cmd, ioev)


class RMSPipeEvent(RMSGatewayLogin, PipeEvent):
    @property
    def callsign(self):
        return ax25_remote_addr(self.io).partition("-")[0].encode("utf-8")


class AX25ListenerEvent(ListenerEvent):
    def __init__(self, spawn_gensio_str, banner=None):
        gw1, rms, gw2 = spawn_gensio_str.partition("rms,")
        self.spawn_gensio_str = gw1 + gw2
        self.banner = banner
        self.pipe = RMSPipeEvent if rms else PipeEvent
        super().__init__()

    @classmethod
    def from_gensio_str(cls, gensio_str, **kwargs):
        accev = cls(**kwargs)
        accev.acc = gensio.gensio_accepter(OSFUNCS, gensio_str, accev)
        accev.acc.startup()
        return accev

    def new_connection(self, acc, io):
        opened_io = super().new_connection(acc, io)
        if opened_io is None:
            return None
        ioev = self.pipe()
        ioev.io = io
        if self.banner is not None:
            ioev.get_write_buffer(ioev.io).extend(f"{self.banner}\r\n".encode("utf-8"))
        ioev.io2 = spawn_for(ioev, self.spawn_gensio_str)
        ioev.io2.open(ioev)
        io.write_cb_enable(True)
        io.read_cb_enable(True)
        return io


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--listen",
        required=True,
        help="Callsign-SSID to listen for AX25 connections.",
    )
    parser.add_argument(
        "-k",
        "--kiss",
        default="tcp,localhost,8001",
        help="Gensio kiss string",
    )
    parser.add_argument(
        "-g",
        "--gateway",
        default="rms,tcp,cms.winlink.org,8772",
        help="Gensio connection string for gateway endpoint.",
    )
    parser.add_argument(
        "--banner",
        default=None,
        help="Text displayed when user connects",
    )

    args = parser.parse_args()

    AX25ListenerEvent.from_gensio_str(
        gensio_str=f"ax25(laddr={args.listen},extended=0),kiss,conacc,{args.kiss}",
        spawn_gensio_str=args.gateway,
        banner=args.banner,
    ).wait()


if __name__ == "__main__":
    main()
