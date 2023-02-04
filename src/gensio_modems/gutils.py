"""Utilities for working with gensio python binding."""

import array
import logging

import gensio


# python-native logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("gutils")


class GensioLogger:
    """gensio internal log callback"""

    def gensio_log(self, level, log):
        logger.debug("***%s log: %s", level, log)


gensio.gensio_set_log_mask(gensio.GENSIO_LOG_MASK_ALL)
OSFUNCS = None


class IOEvent:
    """
    Buffered gensio wrapper.

    i = IOEvent()
    i.io = gensio.gensio(OSFUNCS, "tcp,localhost,3333", i)
    i.io.open(i)
    i.wait()
    """

    def __init__(self):
        self.logger = logging.getLogger(type(self).__name__)
        self._io = None
        # io reads into bufA
        self.bufA = array.array("B")
        # io writes from bufB
        self.bufB = array.array("B")
        self.in_close = False  # true if either gensio is down or going down
        self.in_error = False  # true if self._io had an error
        self.waiter = gensio.waiter(OSFUNCS)

    @property
    def io(self):
        return self._io

    @io.setter
    def io(self, value):
        self._io = value
        if self._io is not None:
            self._io.set_cbs(self)

    def name_for(self, io):
        if io.same_as(self.io):
            return "io"
        raise ValueError("Unknown io: {!r}".format(io))

    def log_for(self, io, message, *args, level=logging.DEBUG, **kwargs):
        """
        Log a message in the context of the given `io`.
        """
        self.logger.log(
            level, "{} {}".format(self.name_for(io), message), *args, **kwargs
        )

    def close(self, io=None):
        self.in_close = True
        if self.io is not None and not self.in_error:
            # with in_close=True, write_callback will close io after buffer is drained
            # (unless there is an error)
            self.io.write_cb_enable(True)
        # if the caller gave us an IO, close it now
        if io is not None:
            # this is the ONLY place to direcly call gensio.close!
            io.close(self)

    def get_read_buffer(self, io):
        if io.same_as(self.io):
            return self.bufA
        raise ValueError("Unknown io: {!r}".format(io))

    def read_callback(self, io, err, data, auxdata):
        if err:
            self.log_for(io, "read: %s", err)
            if "remote end closed connection" not in str(err).lower():
                self.log_for(io, "read error: %s", err)
            self.in_error = True
            self.close(io)
        if self.in_error:
            return 0
        if data:
            self.log_for(io, "read_callback: data=%r", data)
            self.get_read_buffer(io).extend(data)
        if self.bufB:
            self.io.write_cb_enable(True)
        return len(data)

    def get_write_buffer(self, io):
        if io.same_as(self.io):
            return self.bufB
        raise ValueError("Unknown io: {!r}".format(io))

    def write_callback(self, io):
        buf = self.get_write_buffer(io)
        if buf and not self.in_error:
            try:
                count = io.write(buf.tobytes(), None)
            except Exception as e:
                self.log_for(io, "write: %s (in_error=%s, in_close=%s, buf=%s)", e, self.in_error, self.in_close, buf)
                if "remote end closed connection" not in str(err).lower():
                    self.log_for(io, "write error: %s", e)
                self.in_error = True
                buf[:] = []  # reset the buffer here to avoid infinite loop on connection drop
                self.close(io)
                return
            self.log_for(io, "write_callback: data=%s", buf[:count].tobytes())
            buf[:] = buf[count:]
        else:
            io.write_cb_enable(False)
            if self.in_close:
                self.close(io)

    def open_done(self, io, err):
        if err:
            self.log_for(io, "open error: %s", err)
            if self.io is not None:
                self.close(io)
                # normally io would be reset in close_done, but that wont
                # get called if the gensio failed to open
                self.io = None
            return
        self.log_for(io, "Opened gensio: %s", io)
        io.write_cb_enable(True)
        io.read_cb_enable(True)

    def close_done(self, io, wake_when_closed=True):
        self.log_for(io, "closed gensio: %s", io)
        setattr(self, self.name_for(io), None)
        if self.io is None and wake_when_closed:
            self.waiter.wake()

    def wait(self):
        if self.io is not None:
            self.waiter.wait(1)


class PipeEvent(IOEvent):
    """
    Connect two gensios and pass data between them.

    p = PipeEvent()
    p.io = gensio.gensio(OSFUNCS, "tcp,localhost,3333", p)
    p.io.open(p)
    p.io2 = gensio.gensio(OSFUNCS, "stdio(self)", p)
    p.io2.open(p)
    p.wait()
    """

    def __init__(self):
        super().__init__()
        self._io2 = None

    @property
    def io2(self):
        return self._io2

    @io2.setter
    def io2(self, value):
        self._io2 = value
        if self._io2 is not None:
            self._io2.set_cbs(self)

    def name_for(self, io):
        if io.same_as(self.io2):
            return "io2"
        return super().name_for(io)

    def close(self, io=None):
        super().close(io)
        if self.io2 is not None and not self.in_error:
            self.io2.write_cb_enable(True)

    def get_read_buffer(self, io):
        if io.same_as(self.io2):
            return self.bufB
        return super().get_read_buffer(io)

    def read_callback(self, io, err, data, auxdata):
        len_data = super().read_callback(io, err, data, auxdata)
        if self.bufA:
            self.io2.write_cb_enable(True)
        return len_data

    def get_write_buffer(self, io):
        if io.same_as(self.io2):
            return self.bufA
        return super().get_write_buffer(io)

    def open_done(self, io, err):
        super().open_done(io, err)
        if err and self.io2 is not None:
            self.close(self.io2)
            self.io2 = None
            return

    def close_done(self, io):
        super().close_done(io, wake_when_closed=False)
        if self.io is None and self.io2 is None:
            self.waiter.wake()

    def wait(self):
        if self.io is not None or self.io2 is not None:
            self.waiter.wait(1)


class ListenerEvent:
    """
    Listen and accept incoming connections.

    listener = ListenerEvent()
    listener.acc = gensio.gensio_accepter(OSFUNCS, "tcp,3333", listener)
    listener.acc.startup()
    listener.wait()
    """

    def __init__(self):
        self.logger = logging.getLogger(type(self).__name__)
        self.acc = None
        self.ios = []
        self.waiter = gensio.waiter(OSFUNCS)
        self.in_shutdown = False

    def log(self, acc, level, logval):
        self.logger.error("gensio acc %s err: %s", level, logval)

    def new_connection(self, acc, io):
        if self.in_shutdown:
            # it will free automatically
            return None
        self.ios.append(io)
        return io

    def check_finish(self):
        if len(self.ios) == 0 and self.acc is None:
            self.waiter.wake()

    def io_closed(self, io):
        """
        Called from gensio `close_done` callback to signal to listener
        that the connection is closed and no longer needs to be tracked.
        """
        for idx, saved_io in enumerate(self.ios):
            if saved_io.same_as(io):
                break
        else:
            self.logger.warning("untracked connection closed: %r", io)
            idx = None
        if idx is not None:
            del self.ios[idx]
        self.check_finish()

    def shutdown_done(self, acc):
        self.acc = None
        self.check_finish()

    def shutdown(self):
        if self.in_shutdown:
            return
        self.in_shutdown = True
        self.acc.shutdown(self)
        for i in self.ios:
            i.close_s()

    def wait(self):
        if self.acc is not None:
            self.waiter.wait(1)


INIT_DONE = False


def init():
    global INIT_DONE
    if INIT_DONE:
        return
    global OSFUNCS
    OSFUNCS = gensio.alloc_gensio_selector(GensioLogger())
    INIT_DONE = True


init()
