import json
import logging
import sys

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "context"):
            payload.update(record.context)
        return json.dumps(payload)

def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

def log_event(logger: logging.Logger, level: int, message: str, **context) -> None:
    logger.log(level, message, extra={"context": context})