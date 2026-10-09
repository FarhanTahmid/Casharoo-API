from rest_framework.views import exception_handler as drf_exception_handler

from ..gates import PlanLimit, record_refusal


def exception_handler(exc, context):
    """DRF's handler, plus a note of every plan refusal for the dashboard."""
    if isinstance(exc, PlanLimit):
        request = context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            record_refusal(exc, user)
    return drf_exception_handler(exc, context)
