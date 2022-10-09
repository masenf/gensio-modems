import gensio

from gensio_modems.gutils import ListenerEvent, OSFUNCS, PipeEvent


class StdioPipeListener(ListenerEvent):
    def new_connection(self, acc, io):
        pev = PipeEvent()
        pev.io = super().new_connection(acc, io)
        pev.io.write_cb_enable(True)
        pev.io.read_cb_enable(True)
        pev.io2 = gensio.gensio(OSFUNCS, "stdio(self)", pev)
        pev.io2.open(pev)


listener = StdioPipeListener()
listener.acc = gensio.gensio_accepter(OSFUNCS, "tcp,3334", listener)
listener.acc.startup()
listener.wait()
