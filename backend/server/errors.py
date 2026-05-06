"""Custom exception types for BSE scraper and processor."""


class ScraperError(Exception):
    """Base exception for scraper operations."""
    pass


class ScraperRetryableError(ScraperError):
    """Temporary error that should be retried (HTTP 429, 503, timeouts)."""
    pass


class ScraperPermanentError(ScraperError):
    """Permanent error that should not be retried (bad PDF, corrupt file)."""
    pass


class ProcessorError(Exception):
    """Base exception for processor operations."""
    pass


class ProcessorPermanentError(ProcessorError):
    """Permanent error in PDF processing (password-protected, corrupted)."""
    pass
