from __future__ import annotations


class NumerisError(Exception):
    def __init__(self, error_code: str, message: str, detail: dict[str, object] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.detail = detail or {}


class ValidationError(NumerisError):
    pass


class GenerationError(NumerisError):
    pass
