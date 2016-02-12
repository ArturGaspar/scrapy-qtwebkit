# -*- coding: utf-8 -*-

SPIDER_MODULES = ['angularjs_hello_name.spider']
NEWSPIDER_MODULE = 'angularjs_hello_name.spider'

DOWNLOADER_MIDDLEWARES = {
    'scrapy_qtwebkit.QtWebKitMiddleware': 200
}

DOWNLOAD_HANDLERS = {
    'data': 'scrapy_qtwebkit.data_downloader.DataURLDownloadHandler'
}

QTWEBKIT_SHOW_WINDOW = True
QTWEBKIT_QT_PLATFORM = "default"
QTWEBKIT_COOKIES_ENABLED = True
COOKIES_ENABLED = False
