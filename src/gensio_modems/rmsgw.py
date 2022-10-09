"""
Mixin for handling Winlink RMS Gateway login.

For use with AX.25 or VARA winlink gateways.
"""


class RMSGatewayLogin:
    """For best results, mix with gutils.PipeEvent."""

    def _handle_login(self, io, err, data):
        if (
            getattr(self, "_cms_logged_in", False)
            or not data
            or err
            or not io.same_as(self.rms_io)
        ):
            return

        ldata = data.strip().lower()
        send_line = None
        if ldata.startswith(b"callsign"):
            send_line = b"%s\r\n" % self.callsign
        elif ldata.startswith(b"password"):
            send_line = b"%s\r\n" % self.password
            self._cms_logged_in = True
        if send_line is not None:
            self.logger.info("_handle_login: data={}".format(ldata))
            self.get_write_buffer(io).extend(send_line)
            io.write_cb_enable(True)
            return True

    def read_callback(self, io, err, data, auxdata):
        if self._handle_login(io, err, data):
            return len(data)
        return super().read_callback(io, err, data, auxdata)

    @property
    def callsign(self):
        return b"N0CALL"

    @property
    def password(self):
        return b"CMSTelnet"

    @property
    def rms_io(self):
        return self.io2

    def close(self, io=None):
        if io and io.same_as(self.rms_io):
            self._cms_logged_in = False
