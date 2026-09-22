from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required


def role_required(*roles):
    """
    Decorator that restricts access to users with specific roles.
    Usage: @role_required('admin', 'super_admin')
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role in roles:
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden(
                'You do not have permission to access this page.'
            )
        return _wrapped_view
    return decorator
