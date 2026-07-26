"""Recommendation service security boundary."""

from .service_authorization import ServiceTokenVerifier

__all__ = ["ServiceTokenVerifier"]
