from __future__ import annotations


class AppError(Exception):
    status_code: int = 500

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404


class BadRequestError(AppError):
    status_code = 400


class ConflictError(AppError):
    """State conflict — e.g. project still generating, image not ready."""
    status_code = 409


class ServiceError(AppError):
    """Unexpected downstream failure (S3, LLM, DB)."""
    status_code = 502
