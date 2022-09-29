"""
VARA Modem Listener.

1. Connect to VARA control port and set MYCALL and LISTEN ON
2. When a CONNECTED is received, then create a PipeEvent from the data port to the program
"""
import array
import logging

import gensio

from .gutils import IOEvent, PipeEvent, OSFUNCS


class VaraControlEvent(IOEvent):
    def __init__(self, laddr, data_port, spawn="stdio(self)"):
        super().__init__()
        self.laddr = laddr
        self.data_port = data_port
        self.spawn = spawn
        self.connected = None
        self.data_pipe = None
        # this will be sent on the first `write_callback`
        self.bufB[:] = array.array(
            "B",
            b"\r".join(
                [
                    f"MYCALL {laddr}".encode("utf-8"),
                    b"LISTEN ON\r",
                ],
            ),
        )

    def establish_data_connection(self):
        if self.data_pipe is not None:
            raise RuntimeError("Data Pipe was already connected...")
        self.data_pipe = PipeEvent()
        self.data_pipe.io = gensio.gensio(
            OSFUNCS,
            f"tcp,localhost,{self.data_port}",
            self.data_pipe,
        )
        self.data_pipe.io.open(self.data_pipe)
        self.data_pipe.io2 = gensio.gensio(OSFUNCS, self.spawn, self.data_pipe)
        self.data_pipe.io2.open(self.data_pipe)

        def both_ends_close_done(*args):
            self.data_pipe = None

        self.data_pipe.both_ends_close_done = both_ends_close_done

    def dispatch(self, command):
        args = command.split()
        command = args[0].lower()
        if command == "connected":
            self.establish_data_connection()
            source, destination = args[1:2]
            if source == self.laddr:
                # we initiated a connection to destination
                self.connected = destination
            else:
                # we accepted a connection from source
                self.connected = source
            self.log_for(self.io, f"Connected: s:{source} -> d:{destination}")
        elif command == "disconnected":
            if self.data_pipe is not None:
                self.data_pipe.close()
            self.connected = None
        elif command == "wrong":
            self.log_for(self.io, f"WRONG!", level=logging.INFO)
        elif command in ["ok", "iamalive"]:
            pass
        else:
            self.log_for(
                self.io,
                f"unrecognized command: {command}",
                level=logging.INFO,
            )

    def read_callback(self, io, err, data, auxdata):
        data_len = super().read_callback(io, err, data, auxdata)
        readBuf = self.get_read_buffer(io)
        if readBuf:
            readBuf[:], commands = (
                array.array("B"),
                readBuf.tobytes().decode("utf-8").strip().splitlines(),
            )
            for command in commands:
                self.dispatch(command)
        return data_len
