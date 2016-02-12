import base64
import re
import urllib

from scrapy.responsetypes import responsetypes
from scrapy.utils.decorators import defers


_token = r'[{}]+'.format(re.escape(''.join(set(map(chr, range(32, 127))) -
                                           set('()<>@,;:\\"/[]?= '))))

_char = set(map(chr, range(127)))
_quoted = r'"(?:[{}]|(?:\\[{}]))*"'.format(re.escape(''.join(_char -
                                                             set('"\\\r'))),
                                           re.escape(''.join(_char)))

_urlchar = r"[\w;/\\?:@&=+$,-_.!~*'()]"


class DataURLDownloadHandler(object):
    def __init__(self, settings):
        super(DataURLDownloadHandler, self).__init__()

    _data_url_pattern = re.compile((r'data:'
                                    r'({token}/{token})?'
                                    r'(?:;{token}=(?:{token}|{quoted}))*'
                                    r'(;base64)?'
                                    r',({urlchar}*)'
                                    ).format(token=_token, quoted=_quoted,
                                             urlchar=_urlchar))

    @defers
    def download_request(self, request, spider):
        # XXX: I think this needs urllib.unquote().
        m = self._data_url_pattern.match(request.url)
        if not m:
            raise ValueError("invalid data URL")
        mimetype, is_base64, data = m.groups()
        data = urllib.unquote(data)
        if is_base64:
            data = base64.b64decode(data)
        respcls = responsetypes.from_mimetype(mimetype)

        return respcls(url=request.url, body=data)
