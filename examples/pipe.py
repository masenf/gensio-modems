import gensio

from gax25.gutils import PipeEvent, OSFUNCS


p = PipeEvent()
p.io = gensio.gensio(OSFUNCS, "tcp,localhost,3333", p)
p.io.open(p)
p.io2 = gensio.gensio(OSFUNCS, "stdio(self)", p)
p.io2.open(p)
p.wait()
