class PlanError(Exception):
    """A failure the API reports to the user, with a stable machine-readable code."""

    status = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidTripError(PlanError):
    status = 400


class NoRouteFoundError(PlanError):
    status = 422


class UpstreamUnavailableError(PlanError):
    """Every provider for a required service failed."""

    status = 502


class PlanNotFoundError(PlanError):
    status = 404
