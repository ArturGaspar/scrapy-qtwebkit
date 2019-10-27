from scrapy.logformatter import LogFormatter as ScrapyLogFormatter


class LogFormatter(ScrapyLogFormatter):
    def crawled(self, request, response, spider):
        log = super().crawled(request, response, spider)
        if request.meta.get('from_browser'):
            log['level'] = 5
        return log
