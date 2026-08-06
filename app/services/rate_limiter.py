import logging
from datetime import datetime, timedelta

from app.core.logging_config import log_event

logger = logging.getLogger("rate_limiter")

COOLDOWN = timedelta(hours=1)

_last_not_found: dict[tuple[str, str], datetime] = {}


def check_cooldown(cnpj: str, access_key: str) -> None:
    key = (cnpj, access_key)
    last = _last_not_found.get(key)

    if last is not None:
        elapsed = datetime.now() - last
        if elapsed < COOLDOWN:
            remaining_minutes = int((COOLDOWN - elapsed).total_seconds() // 60) + 1
            log_event(
                logger, logging.WARNING, "cooldown active, blocking request",
                access_key=access_key, cnpj=cnpj, remaining_minutes=remaining_minutes,
            )
            raise RateLimitError(
                f"Aguarde ~{remaining_minutes} min antes de consultar essa chave de novo "
                f"(regra de uso indevido da SEFAZ — evitar bloqueio de 1h)"
            )


def register_not_found(cnpj: str, access_key: str) -> None:
    _last_not_found[(cnpj, access_key)] = datetime.now()


class RateLimitError(Exception):
    """Raised locally to prevent a request that would trigger SEFAZ's own anti-abuse block."""
