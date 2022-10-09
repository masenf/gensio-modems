#!/usr/bin/python3
"""
gAXlisten - listen for ax25 connections to hand off to a program or console
"""

import array
import argparse
import logging
import shlex
import subprocess
import sys

import gensio


# python-native logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("gaxlisten")


class GensioLogger:
    """gensio internal log callback"""

    def gensio_log(self, level, log):
        logger.debug("***%s log: %s", level, log)


gensio.gensio_set_log_mask(gensio.GENSIO_LOG_MASK_ALL)
o = gensio.alloc_gensio_selector(GensioLogger())


def ax25_remote_addr(io):
    raddr = io.control(0, True, gensio.GENSIO_CONTROL_RADDR, b"")
    gensio_name, _, addr_str = raddr.partition(":")
    addrs = addr_str.split(",")
    return addrs[1] if len(addrs) > 1 else addrs[0]


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


DEFAULT_FILTER = "xlt(lfcr)"


def spawn_for(ioev, command, g_filter=None, stderr=False):
    g_string = "stdio(self)"
    if command:
        sh_cmd = ax25_command_substitution(ioev.io, shlex.join(command))
        logger.info("spawn: {}".format(sh_cmd))
        g_string = ("stdio(stderr-to-stdout)," if stderr else "stdio,") + sh_cmd
    #    if g_filter is None:
    #        g_filter = DEFAULT_FILTER
    if g_filter:
        g_string = "{},{}".format(g_filter, g_string)
    return gensio.gensio(o, g_string, ioev)


class IOEvent:
    def __init__(self, accev):
        self.accev = accev
        self._io = None  # the ax25 listener side of the connection
        self._io2 = None  # established on demand to interface with a process or console
        # io reads into bufA and io2 writes from bufA
        self.bufA = array.array("B")
        # io writes from bufB and io2 reads into bufB
        self.bufB = array.array("B")
        self.in_close = False  # true if either gensio is down or going down

    @property
    def io(self):
        return self._io

    @io.setter
    def io(self, value):
        self._io = value
        if self._io is not None:
            self._io.set_cbs(self)

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
        self.io.write_cb_enable(True)
        self.io2.write_cb_enable(True)
        io.close(self)

    def get_read_buffer(self, io):
        if io.same_as(self.io):
            return self.bufA
        elif io.same_as(self.io2):
            return self.bufB
        raise ValueError("Unknown io: {!r}".format(io))

    def read_callback(self, io, err, data, auxdata):
        if err:
            self.log_for(io, "read: %s", err)
            if err != "Remote end closed connection":
                self.log_for(io, "read error: %s", err)
            self.close(io)
            return 0
        if data:
            self.log_for(io, "read_callback: data=%r", data)
            self.get_read_buffer(io).extend(data)
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
            io.close(self)
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
    def __init__(self, command, stderr):
        self.ios = []
        self.waiter = gensio.waiter(o)
        self.in_shutdown = False
        self.command = command
        self.stderr = stderr

    def log(self, acc, level, logval):
        logger.error("gensio acc %s err: %s", level, logval)

    def new_connection(self, acc, io):
        if self.in_shutdown:
            # it will free automatically
            return
        ioev = IOEvent(self)
        logger.info("accepted new connection: %r", io)
        ioev.io = io
        ioev.io2 = spawn_for(ioev, self.command, stderr=self.stderr)
        ioev.io2.open(ioev)
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
    parser.add_argument("-l", "--listen", help="AX.25 SSID to listen on")
    parser.add_argument(
        "-k",
        "--kiss",
        default="tcp,localhost,8001",
        help="gensio kiss connection string",
    )
    parser.add_argument(
        "--stderr",
        action="store_true",
        default=False,
        help="Also send stderr over AX.25 connection",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    accev = AccEvent(command=args.command, stderr=args.stderr)
    accev.acc = gensio.gensio_accepter(
        o,
        f"ax25(laddr={args.listen},extended=0),kiss,conacc,{args.kiss}",
        accev,
    )
    accev.acc.startup()
    accev.wait()


if __name__ == "__main__":
    main()
