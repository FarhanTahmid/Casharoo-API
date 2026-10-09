from .entitlements import begin_request_cache, end_request_cache


class EntitlementsCacheMiddleware:
    """A request works out each user's entitlements once and reuses them until it ends."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = begin_request_cache()
        try:
            return self.get_response(request)
        finally:
            end_request_cache(token)
