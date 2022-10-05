"""
VARA Modem Listener.
"""
import array
import logging
import time

import gensio

from .gutils import IOEvent, PipeEvent, OSFUNCS
from .rmsgw import RMSGatewayLogin


logger = logging.getLogger("vara")


WAIT_FOR_DISCONNECT = 120
WAIT_FOR_STEP_MSEC = 1000


class VaraPipeEvent(PipeEvent):
    def __init__(self, vara_control):
        super().__init__()
        self.vara_control = vara_control

    def connect_channel(self, spawn):
        self.reset_channel()
        # connect the program/console
        self.io2 = gensio.gensio(OSFUNCS, spawn, self)
        self.io2.open(self)

    def close_channel(self):
        self.close(self.io2)

    def reset_channel(self):
        # clean up any buffer remnants
        buf = self.bufA  # io2 writes from bufA
        buf[:] = buf[1:0]
        self.in_close = False

    def graceful_disconnect(self):
        self.vara_control.execute("DISCONNECT")
        # wait until VARA acknowledges the disconnect
        abort = time.time() + (WAIT_FOR_DISCONNECT * 0.9)
        expire = time.time() + WAIT_FOR_DISCONNECT
        while True:
            if time.time() > abort:
                self.vara_control.execute("ABORT")
                abort = float("inf")  # dont abort again
            if time.time() > expire:
                self.logger.error("VARA control never signaled disconnect.")
                break
            if not self.vara_control.connected:
                break
            self.waiter.wait_timeout(1, WAIT_FOR_STEP_MSEC)

    def close(self, io=None):
        if (io is not None and io.same_as(self.io)) or self.vara_control.in_shutdown:
            if self.vara_control.connected:
                try:
                    self.graceful_disconnect()
                except Exception as exc:
                    self.logger.exception("Unhandled Exception in graceful_disconnect")
            if not self.vara_control.in_shutdown:
                # Note: we do NOT want to close the VARA side of the data connection
                #       until we're shutting down the control side as well.
                return
        super().close(io)


class VaraRMSPipeEvent(RMSGatewayLogin, VaraPipeEvent):
    @property
    def callsign(self):
        return self.vara_control.laddr.partition("-")[0].encode("utf-8")


DEFAULT_SPAWN = "stdio(self)"


class VaraControlEvent(IOEvent):
    def __init__(self, laddr, data_port, spawn=None, banner=None, rms=False):
        super().__init__()
        self.laddr = laddr
        self.data_port = data_port
        self.spawn = spawn or DEFAULT_SPAWN
        self.banner = banner
        self.connected = None
        self.in_shutdown = False
        if rms:
            pipe = VaraRMSPipeEvent
        else:
            pipe = VaraPipeEvent
        self.data_pipe = self.establish_data_connection(pipe=pipe)
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

    @classmethod
    def from_gensio_str(cls, gensio_str, **kwargs):
        vc = cls(**kwargs)
        vc.io = gensio.gensio(OSFUNCS, gensio_str, vc)
        vc.io.open(vc)
        return vc

    def establish_data_connection(self, pipe=VaraPipeEvent):
        data_pipe = pipe(vara_control=self)
        data_pipe.io = gensio.gensio(
            OSFUNCS,
            self.data_port,
            data_pipe,
        )
        data_pipe.io.open(data_pipe)
        return data_pipe

    def dispatch(self, command):
        args = command.split()
        command = args[0].lower()
        if command == "connected":
            source, destination = args[1:3]
            if source == self.laddr:
                # we initiated a connection to destination
                self.connected = destination
            else:
                # we accepted a connection from source
                self.connected = source
            try:
                self.data_pipe.connect_channel(self.spawn)
            except Exception:
                self.log_for(self.io, f"Connection failed", exc_info=True)
                self.data_pipe.close_channel()
                return
            if self.banner is not None:
                self.data_pipe.bufB.extend(f"{self.banner}\r\n".encode("utf-8"))
            self.log_for(self.io, f"Connected: s:{source} -> d:{destination}")
        elif command == "disconnected":
            disconnected_from = self.connected
            self.connected = None
            if self.data_pipe is not None:
                self.data_pipe.reset_channel()
            self.logger.info(f"Disconnected from {disconnected_from}")
        elif command == "wrong":
            self.log_for(self.io, f"WRONG!", level=logging.INFO)
        elif command in [
            "ok",
            "iamalive",
            "ptt",
            "buffer",
            "registered",
            "link",
            "pending",
            "cancelpending",
            "busy",
        ]:
            # these commands are all ignored at this point
            pass
        else:
            self.log_for(
                self.io,
                f"unrecognized command: {command}",
                level=logging.INFO,
            )

    def execute(self, *args):
        def encode_utf8(obj):
            if not isinstance(obj, bytes):
                return str(obj).encode("utf-8")

        self.bufB.extend(
            b" ".join(encode_utf8(a) for a in args) + b"\r",
        )
        if self.io is not None:
            # schedule to send if we didn't already close
            self.io.write_cb_enable(True)

    def read_callback(self, io, err, data, auxdata):
        data_len = super().read_callback(io, err, data, auxdata)
        if err:
            return data_len
        if self.data_pipe.io is None:
            self.close()
            return data_len
        readBuf = self.get_read_buffer(io)
        if readBuf:
            readBuf[:], commands = (
                array.array("B"),
                readBuf.tobytes().decode("utf-8").strip().splitlines(),
            )
            for command in commands:
                try:
                    self.dispatch(command)
                except Exception as exc:
                    self.logger.exception("Unhandled Exception in dispatch")
        return data_len

    def close(self, io=None):
        self.in_shutdown = True
        self.data_pipe.close()
        super().close(io)

    def wait_till_close(self):
        while self.io is not None:
            try:
                self.wait()
            except KeyboardInterrupt:
                if self.in_close:
                    raise  # second interrupt kills us
                self.logger.info("Interrupt, closing modem...")
            finally:
                self.close()
