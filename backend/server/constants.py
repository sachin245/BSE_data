"""Application-wide constants for BSE scraper and processor."""


class LogConfig:
    """Logging configuration constants."""
    MAX_ENTRIES: int = 500
    TRIM_THRESHOLD: int = 100


class HttpConfig:
    """HTTP client configuration constants."""
    DEFAULT_TIMEOUT_SEC: float = 30.0
    SESSION_TIMEOUT_SEC: float = 20.0
    SCRIP_NAME_TIMEOUT_SEC: float = 10.0
    MAX_RETRIES: int = 5
    BACKOFF_MIN_SEC: float = 2.0
    BACKOFF_MAX_SEC: float = 32.0
    PDF_RETRY_429_WAIT_SEC: float = 8.0
    PDF_RETRY_503_WAIT_SEC: float = 4.0
    PDF_RETRY_ATTEMPTS: int = 2


class BseUrls:
    """BSE-related URL constants."""
    HOME: str = "https://www.bseindia.com/"
    API_BASE: str = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
    ATTACH_BASE: str = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
    ANN_REFERER: str = "https://www.bseindia.com/corporates/ann.html"
    SCRIP_HEADER_API: str = "https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"


class PathConfig:
    """File system paths."""
    DATA_DIR: str = "data"
    ATTACHMENTS_DIR: str = "data/attachments"
    DB_PATH: str = "data/announcements.db"
    CONFIG_PATH: str = "data/config.json"
    LOGS_DIR: str = "logs"


class DefaultUserAgent:
    """Default User-Agent strings."""
    CHROME: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
