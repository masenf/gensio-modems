import logging

import gensio

from gax25.vara import VaraControlEvent
from gax25.gutils import OSFUNCS


SPAWN = "xlt(crlf),telnet,tcp,muck.universitymuck.org,2052"
SPAWN = "tcp,india.colorado.edu,13"
SPAWN = "tcp,telehack.com,23"
SPAWN = "tcp,cms.winlink.org,8772"


VaraControlEvent.from_gensio_str(
    "tcp,localhost,8300",
    laddr="KF7HVM-10",
    data_port="tcp,localhost,8301",
    spawn=SPAWN,
).wait_till_close()
