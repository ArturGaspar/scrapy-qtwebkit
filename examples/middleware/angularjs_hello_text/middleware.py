from urlparse import urlparse

from scrapy.exceptions import IgnoreRequest


class BlockRequestsMiddleware(object):
    def process_request(self, request, spider):
        if request.meta.get('from_qtwebkit', False):
            ext = urlparse(request.url).path.rsplit('.', 1)[-1]
            if ext in {'css', 'gif', 'png'}:
                raise IgnoreRequest()
