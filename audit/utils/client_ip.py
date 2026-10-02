from django.conf import settings


def get_client_ip(request):
    """
    Get client IP address from request.

    X-Forwarded-For can be set to anything by the client, so it is only read
    when the app sits behind proxies we run (settings.TRUSTED_PROXY_COUNT).
    Each trusted proxy appends the address it saw, so the client address is
    the Nth entry from the right.
    """
    proxy_count = getattr(settings, 'TRUSTED_PROXY_COUNT', 0)
    if proxy_count > 0:
        forwarded = [ip.strip() for ip in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if ip.strip()]
        if len(forwarded) >= proxy_count:
            return forwarded[-proxy_count]
    return request.META.get('REMOTE_ADDR')
