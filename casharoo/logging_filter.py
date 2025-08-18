import logging

class LevelRangeFilter(logging.Filter):
    """Allow records whose levelno is between min_level and max_level (inclusive)."""
    def __init__(self, min_level=logging.NOTSET, max_level=logging.CRITICAL):
        super().__init__()
        self.min_level = min_level
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return self.min_level <= record.levelno <= self.max_level