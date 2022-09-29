import gensio

from gax25.vara import VaraControlEvent
from gax25.gutils import OSFUNCS


vc = VaraControlEvent(laddr="KF7HVM-10", data_port=8301)
vc.io = gensio.gensio(OSFUNCS, "tcp,localhost,8300", vc)
vc.io.open(vc)
vc.wait()
