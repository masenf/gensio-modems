import array
import logging


logger = logging.getLogger("varaio")


class VaraListener:
    def __init__(self, laddr, data_port, spawn="stdio(self)"):
        self.laddr = laddr
        self.data_port = data_port
        self.spawn = spawn
        self.connected = None
        self._io = None  # the vara command side of the connection
        self.bufIn = array.array("B")
        # this will be sent on the first `write_callback`
        self.bufOut = array.array(
            "B",
            "\r".join(
                [
                    f"MYCALL {laddr}".encode("utf-8"),
                    "LISTEN ON",
                ],
            )
        )
        self.in_close = False  # true if either gensio is down or going down

    @property
    def io(self):
        return self._io

    @io.setter
    def io(self, value):
        self._io = value
        if self._io is not None:
            self._io.set_cbs(self)

    def close(self, io):
        self.in_close = True
        self.io.write_cb_enable(True)

    def dispatch(self, command):
        """Handle incoming command from VARA modem."""
        args = command.lower().split()
        if args[0] == "connected":
            # Connect the spawn gensio and the VARA data port together
            pass



    def read_callback(self, io, err, data, auxdata):
        if err:
            if err != "Remote end closed connection":
                self.log_for(io, "read error: %s", err)
            self.close(io)
            return 0
        if data:
            logger.debug("read_callback: data=%r", data)
            for command in data.splitlines():
            self.bufIn.extend(data)
        if self.bufOut:
            self.io.write_cb_enable(True)
        return len(data)

    def write_callback(self, io):
        buf = self.bufOut
        if buf:
            try:
                count = io.write(buf.tobytes(), None)
            except Exception as e:
                if str(e) != "Remote end closed connection":
                    logger.error("write error: %s", e)
                self.close(io)
                return
            logger.debug(io, "write_callback: data=%s", buf[:count].tobytes())
            buf[:] = buf[count:]

        if not buf:
            io.write_cb_enable(False)
            if self.in_close:
                io.close(self)

    def open_done(self, io, err):
        if err:
            logger.error("open error: %s", err)
            io.close(self)
            if self.io is not None:
                self.io.close(self)
            return
        logger.info(io, "Opened gensio: %s", io)
        io.write_cb_enable(True)
        io.read_cb_enable(True)

    def close_done(self, io):
        self.log_for(io, "closed gensio: %s", io)


