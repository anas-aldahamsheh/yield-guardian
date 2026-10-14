"""Service errors of the API's own stores, mapped to problem+json like every ServiceError."""

from yield_guardian.contracts.services import ServiceError


class ConflictError(ServiceError):
    """The resource is not in a state that allows the request."""

    code = "conflict"
    status = 409
    title = "Conflict"


class AuthenticationError(ServiceError):
    code = "unauthorized"
    status = 401
    title = "Sign-in failed"
