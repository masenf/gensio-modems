import argparse

from gax25.vara import VaraControlEvent


"""
Some other ideas for spawning a gateway
SPAWN = "tcp,india.colorado.edu,13"   # time
SPAWN = "tcp,telehack.com,23"         # sort of shell
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--listen",
        required=True,
        help="Callsign-SSID to listen for VARA connections.",
    )
    parser.add_argument(
        "-p",
        "--vara-port",
        default=8300,
        help="Control port for VARA or VARA FM",
    )
    parser.add_argument(
        "--vara-host",
        default="localhost",
        help="Host running VARA or VARA FM",
    )
    parser.add_argument(
        "--gateway",
        default="rms,tcp,cms.winlink.org,8772",
        help="Gensio connection string for gateway endpoint.",
    )
    parser.add_argument(
        "--banner",
        default=None,
        help="Text displayed when user connects",
    )

    args = parser.parse_args()

    gw1, rms, gw2 = args.gateway.partition("rms,")

    VaraControlEvent.from_gensio_str(
        gensio_str=f"tcp,{args.vara_host},{args.vara_port}",
        laddr=args.listen,
        data_port=f"tcp,{args.vara_host},{int(args.vara_port)+1}",
        spawn=gw1 + gw2,
        banner=args.banner,
        rms=bool(rms),
    ).wait_till_close()


if __name__ == "__main__":
    main()
