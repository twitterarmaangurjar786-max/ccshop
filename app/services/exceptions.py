"""Domain-specific exceptions used across services."""
from __future__ import annotations


class ServiceError(Exception):
    """Base class for user-facing service errors."""


class InsufficientFunds(ServiceError):
    pass


class OutOfStock(ServiceError):
    pass


class ReservationExpired(ServiceError):
    pass


class SellerExists(ServiceError):
    pass


class SellerNotFound(ServiceError):
    pass


class InvalidInput(ServiceError):
    pass


class CouponError(ServiceError):
    pass


class NotAuthorized(ServiceError):
    pass
