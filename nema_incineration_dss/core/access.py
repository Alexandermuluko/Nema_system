from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import UserProfile


def has_role(user, role):
    try:
        stored_role = user.profile.role
    except UserProfile.DoesNotExist:
        stored_role = ""
    if role == UserProfile.ROLE_ADMIN and user.is_superuser:
        return True
    return stored_role == role


def role_required(role):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, role):
                messages.error(request, "You are not authorized to access that page.")
                return redirect("admin_dashboard" if has_role(request.user, UserProfile.ROLE_ADMIN) else "dashboard")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


officer_required = role_required(UserProfile.ROLE_OFFICER)
admin_required = role_required(UserProfile.ROLE_ADMIN)