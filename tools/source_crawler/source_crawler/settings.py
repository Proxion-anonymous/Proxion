# Scrapy settings for source_crawler project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from pathlib import Path

BOT_NAME = "source_crawler"

SPIDER_MODULES = ["source_crawler.spiders"]
NEWSPIDER_MODULE = "source_crawler.spiders"

# Postgres settings
POSTGRES_HOST = str(Path.home() / "Documents/ProxyChecker/.postgres-socket")
POSTGRES_DATABASE = "proxychecker"
POSTGRES_USER = "proxychecker"
POSTGRES_PASSWORD = "proxychecker"

# Crawl responsibly by identifying yourself (and your website) on the user-agent
# USER_AGENT = "source_crawler (+http://www.yourdomain.com)"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/119.0"

# Obey robots.txt rules
# ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
# CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
# DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
# CONCURRENT_REQUESTS_PER_DOMAIN = 16
# CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
# COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
# TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    #    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    #    "Accept-Language": "en",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,en-US;q=0.7,en;q=0.3",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cookie": "cf_chl_2=ac5baad981bcd12; _ga_T1JC9RNQXV=GS1.1.1699868665.1.0.1699868665.60.0.0; cf_clearance=K0nbYXJR4vEXgW1TmNioJARxrdBFGCKBbZ_AzEad04o-1699868665-0-1-41cc3539.fc214495.16cd6ad9-150.2.1699868665; ASP.NET_SessionId=lyissmrlec3t3xi5e0ydma3n; __cflb=02DiuFnsSsHWYH8WqVXbZzkeTrZ6gtmGVTfUJimNh5Eig; _ga=GA1.2.303306938.1699868665; _gid=GA1.2.1503739041.1699868665; _gat_gtag_UA_46998878_6=1; etherscan_offset_datetime=+8",
}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# SPIDER_MIDDLEWARES = {
#    "source_crawler.middlewares.SourceCrawlerSpiderMiddleware": 543,
# }

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
# DOWNLOADER_MIDDLEWARES = {
#    "source_crawler.middlewares.SourceCrawlerDownloaderMiddleware": 543,
# }

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
# EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
# }

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
# Items go through from lower valued to higher valued classes
ITEM_PIPELINES = {
    # "source_crawler.pipelines.SourceCombinePipeline": 200,
    # "source_crawler.pipelines.SourceValidatePipeline": 300,
    # "source_crawler.pipelines.MongoDBPipeline": 400,
    "source_crawler.pipelines.PostgresPipeline": 400,
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = True
# The initial download delay
AUTOTHROTTLE_START_DELAY = 1
# The maximum download delay to be set in case of high latencies
AUTOTHROTTLE_MAX_DELAY = 5
# The average number of requests Scrapy should be sending in parallel to
# each remote server
AUTOTHROTTLE_TARGET_CONCURRENCY = 5.0
# Enable showing throttling stats for every response received:
AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
# HTTPCACHE_ENABLED = True
# HTTPCACHE_EXPIRATION_SECS = 0
# HTTPCACHE_DIR = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = []
# HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
