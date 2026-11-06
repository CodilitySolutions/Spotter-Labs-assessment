"""Every API error uses one shape: ``{"error": {"code", "message", "details"?}}``."""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from ..services.errors import PlanError

log = logging.getLogger(__name__)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, PlanError):
        return _error(exc.status, exc.code, exc.message)

    if isinstance(exc, exceptions.ValidationError):
        return _error(
            status.HTTP_400_BAD_REQUEST,
            "invalid_request",
            "Some fields are missing or invalid.",
            details=exc.detail,
        )

    response = exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "error")
        message = str(getattr(exc, "detail", "Request failed."))
        return _error(response.status_code, code, message)

    log.exception("Unhandled API error")
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Something went wrong.")


def _error(http_status: int, code: str, message: str, details: Any = None) -> Response:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return Response({"error": body}, status=http_status)
