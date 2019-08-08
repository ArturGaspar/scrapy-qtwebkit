# Copyright (c) Scrapy developers.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     1. Redistributions of source code must retain the above copyright notice,
#        this list of conditions and the following disclaimer.
#
#     2. Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in the
#        documentation and/or other materials provided with the distribution.
#
#     3. Neither the name of Scrapy nor the names of its contributors may be
#        used to endorse or promote products derived from this software without
#        specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


from http.cookiejar import IPV4_RE
from urllib.parse import urlparse
from urllib.request import Request


def _potential_domain_matches(domain):
    """

    Potential domain matches for a cookie.

    >>> _potential_domain_matches('www.example.com')
    ['www.example.com', 'example.com', '.www.example.com', '.example.com']

    From scrapy.http.cookies.potential_domain_matches().

    """

    matches = [domain]
    try:
        start = domain.index('.') + 1
        end = domain.rindex('.')
        while start < end:
            matches.append(domain[start:])
            start = domain.index('.', start) + 1
    except ValueError:
        pass
    return matches + ['.' + d for d in matches]


def cookies_for_url(jar, url):
    """

    Get cookies for an URL from a cookielib CookieJar.

    Adapted from scrapy.http.cookies.CookieJar.add_cookie_header().

    """

    host = urlparse(url).hostname
    if not IPV4_RE.search(host):
        hosts = _potential_domain_matches(host)
        if host.find(".") == -1:
            hosts += host + ".local"
    else:
        hosts = [host]

    for host in hosts:
        if host in jar._cookies:
            # TODO: origin and unverifiable.
            req = Request(url)
            for cookie in jar._cookies_for_domain(host, req):
                yield cookie
