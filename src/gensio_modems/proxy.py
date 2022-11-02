#!/usr/bin/python3
"""
gAXproxy - proxy an AX.25 connection over telnet.

use with pat to establish a "telnet" connection that uses gensio for
AX.25 transport.
"""

import array
import argparse
import logging
import re
import shlex
import subprocess
import sys

import gensio


# python-native logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("gaxproxy")

CRED_PROMPTS = [b"Callsign :\r", b"Password :\r"]


class GensioLogger:
    """gensio internal log callback"""

    def gensio_log(self, level, log):
        logger.debug("***%s log: %s", level, log)


gensio.gensio_set_log_mask(gensio.GENSIO_LOG_MASK_ALL)
o = gensio.alloc_gensio_selector(GensioLogger())


def replace_positional(endpoint, *args):
    for ix, val in enumerate(args):
        endpoint = endpoint.replace(f"%{ix}", val)
    return endpoint


def spawn_for(ioev, endpoint):
    logger.info(f"spawning {endpoint}")
    return gensio.gensio(o, endpoint, ioev)


class IOEvent:
    def __init__(self, accev, require_creds=1):
        self.accev = accev
        self._io = None  # the "listener" end, typically telnet connection
        self._io2 = None  # established on demand to make an ax25 connection
        # io reads into bufA and io2 writes from bufA
        self.bufA = array.array("B")
        # io writes from bufB and io2 reads into bufB
        self.bufB = array.array("B")
        self.in_close = False  # true if either gensio is down or going down
        self.require_creds = require_creds
        self.creds = []
        if self.require_creds == 1:
            # the "Password"-only style
            self.bufB.extend(CRED_PROMPTS[1])
        elif self.require_creds:
            self.bufB.extend(CRED_PROMPTS[0])

    @property
    def io(self):
        return self._io

    @io.setter
    def io(self, value):
        self._io = value
        if self._io is not None:
            self._io.set_cbs(self)
            self.spawn_io2_when_ready()

    @property
    def io2(self):
        return self._io2

    @io2.setter
    def io2(self, value):
        self._io2 = value
        if self._io2 is not None:
            self._io2.set_cbs(self)

    def name_for(self, io):
        if io.same_as(self.io):
            return "io"
        elif io.same_as(self.io2):
            return "io2"
        raise ValueError("Unknown io: {!r}".format(io))

    def log_for(self, io, message, *args, level=logging.DEBUG, **kwargs):
        """
        Log a message in the context of the given `io`.
        """
        logger.log(level, "{} {}".format(self.name_for(io), message), *args, **kwargs)

    def close(self, io):
        self.in_close = True
        # with in_close=True, write_callback will close io after buffer is drained
        self.io.write_cb_enable(True)
        self.io2.write_cb_enable(True)
        io.close(self)

    def get_read_buffer(self, io):
        if io.same_as(self.io):
            return self.bufA
        elif io.same_as(self.io2):
            return self.bufB
        raise ValueError("Unknown io: {!r}".format(io))

    def spawn_io2_when_ready(self):
        if (
            self.io2 is None
            and len(self.creds) >= self.require_creds
            and not self.in_close
        ):
            # once creds are received, spawn and connect the second endpoint
            self.io2 = spawn_for(
                ioev=self,
                endpoint=replace_positional(self.accev.endpoint, *self.creds),
            )
            self.io2.open(self)

    def read_callback(self, io, err, data, auxdata):
        if err:
            self.log_for(io, "read: %s", err)
            if err != "Remote end closed connection":
                self.log_for(io, "read error: %s", err)
            self.close(io)
            return 0
        if data:
            self.log_for(io, "read_callback: data=%r", data)
            if len(self.creds) < self.require_creds and io.same_as(self.io):
                self.creds.append(data.decode("utf-8").strip())
                if len(self.creds) < self.require_creds:
                    self.bufB.extend(CRED_PROMPTS[len(self.creds) % len(CRED_PROMPTS)])
            else:
                self.get_read_buffer(io).extend(data)
        self.spawn_io2_when_ready()
        if self.bufA:
            self.io2.write_cb_enable(True)
        if self.bufB:
            self.io.write_cb_enable(True)
        return len(data)

    def get_write_buffer(self, io):
        if io.same_as(self.io):
            return self.bufB
        elif io.same_as(self.io2):
            return self.bufA
        raise ValueError("Unknown io: {!r}".format(io))

    def write_callback(self, io):
        buf = self.get_write_buffer(io)
        if buf:
            try:
                count = io.write(buf.tobytes(), None)
            except Exception as e:
                self.log_for(io, "write: %s", e)
                if str(e) != "Remote end closed connection":
                    self.log_for(io, "write error: %s", e)
                self.close(io)
                return
            self.log_for(io, "write_callback: data=%s", buf[:count].tobytes())
            buf[:] = buf[count:]

        if not buf:
            io.write_cb_enable(False)
            if self.in_close:
                io.close(self)

    def open_done(self, io, err):
        if err:
            self.log_for(io, "open error: %s", err)
            if self.io is not None:
                self.io.close(self)
            if self.io2 is not None:
                self.io2.close(self)
            return
        self.log_for(io, "Opened gensio: %s", io)
        io.write_cb_enable(True)
        io.read_cb_enable(True)

    def close_done(self, io):
        self.log_for(io, "closed gensio: %s", io)
        setattr(self, self.name_for(io), None)
        if self.io is None and self.io2 is None:
            self.accev.io_closed(self)

            # Break reference loops
            self.accev = None


class AccEvent:
    def __init__(self, endpoint, require_creds):
        self.ios = []
        self.waiter = gensio.waiter(o)
        self.endpoint = endpoint
        self.require_creds = require_creds
        self.in_shutdown = False

    def log(self, acc, level, logval):
        logger.error("gensio acc %s err: %s", level, logval)

    def new_connection(self, acc, io):
        if self.in_shutdown:
            # it will free automatically
            return
        ioev = IOEvent(self, require_creds=self.require_creds)
        logger.info("accepted new connection: %r", io)
        ioev.io = io
        self.ios.append(ioev)
        # enable callbacks explicitly, since io is already open so
        # IOEvent.open_done will not be called
        io.write_cb_enable(True)
        io.read_cb_enable(True)

    def check_finish(self):
        if len(self.ios) == 0 and self.acc is None:
            self.waiter.wake()

    def io_closed(self, ioev):
        i = self.ios.index(ioev)
        del self.ios[i]
        logger.info("connection closed: %r", ioev)
        self.check_finish()

    def shutdown_done(self, acc):
        self.acc = None
        self.check_finish()

    def shutdown(self, ioev):
        if self.in_shutdown:
            return
        self.in_shutdown = True
        self.acc.shutdown(self)
        for i in self.ios:
            if i != ioev:
                # The caller will close itself, let it finish its write
                i.close(io)

    def wait(self):
        self.waiter.wait(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--mycall", help="my callsign")
    parser.add_argument(
        "--ax25-conf",
        default="extended=0,retries=2",
        help="parameters passed to gensio ax25 module",
    )
    parser.add_argument(
        "-l", "--listen", default="tcp,localhost,8772", help="gensio spec to listen on"
    )
    parser.add_argument(
        "--require-creds",
        default=1,
        help="Prompt for 'credentials' on listener (can be replaced as %%n in --gateway",
    )
    parser.add_argument(
        "-g",
        "--gateway",
        default="%0",
        help="gateway callsign to connect to; defaults to the provided 'password'",
    )
    parser.add_argument(
        "-k",
        "--kiss",
        default="tcp,localhost,8001",
        help="gensio kiss connection string",
    )
    args = parser.parse_args()

    endpoint_conf = args.ax25_conf
    if not re.search(r"\bladder=", endpoint_conf):
        endpoint_conf = f"laddr={args.mycall}," + endpoint_conf
    if not re.search(r"\badder=", endpoint_conf):
        endpoint_conf = f'addr="0,{args.gateway},{args.mycall}",' + endpoint_conf

    accev = AccEvent(
        endpoint=f"ax25({endpoint_conf}),kiss,{args.kiss}",
        require_creds=int(args.require_creds),
    )
    accev.acc = gensio.gensio_accepter(o, args.listen, accev)
    accev.acc.startup()
    accev.wait()


if __name__ == "__main__":
    main()
