"""Error types with secret-safe messages."""

from __future__ import annotations

from typing import Any


class BiohubESMError(RuntimeError):
    """Base error for deterministic plugin helpers."""


class ValidationError(BiohubESMError, ValueError):
    """Input failed local validation before provider submission."""


class SchemaDriftError(BiohubESMError):
    """A public alpha response no longer matches the contract we validated."""

    def __init__(self, message: str, *, raw: Any = None) -> None:
        super().__init__(message)
        self.raw = raw
        self.diagnostic_path: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": "schema-drift",
            "message": str(self),
            "raw_response_available": self.raw is not None,
        }
        if self.diagnostic_path:
            result["diagnostic_path"] = self.diagnostic_path
        return result


class APIError(BiohubESMError):
    """Normalized provider failure without response secrets."""

    def __init__(
        self,
        *,
        status: int | None,
        kind: str,
        message: str,
        retry_after: float | None = None,
        partial: bool = False,
        response_body_partial: bool = False,
        operation_indeterminate: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.retry_after = retry_after
        self.partial = partial
        self.response_body_partial = response_body_partial
        self.operation_indeterminate = (
            (
                (status is None and kind in {"network", "timeout"})
                or (
                    isinstance(status, int) and not isinstance(status, bool) and 100 <= status < 200
                )
            )
            if operation_indeterminate is None
            else operation_indeterminate
        )

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "status": self.status,
            "kind": self.kind,
            "message": str(self),
            "retry_after": self.retry_after,
            "partial": self.partial,
            "response_body_partial": self.response_body_partial,
            "operation_indeterminate": self.operation_indeterminate,
        }
        provider_status = getattr(self, "provider_status", None)
        if (
            isinstance(provider_status, int)
            and not isinstance(provider_status, bool)
            and 100 <= provider_status <= 599
        ):
            result["provider_status"] = provider_status
        return result
