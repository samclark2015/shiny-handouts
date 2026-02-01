"""
Timezone middleware to convert UTC times to user's local timezone.

Reads timezone from a cookie set by JavaScript and activates it for the request.
"""

import zoneinfo

from django.utils import timezone


class TimezoneMiddleware:
    """
    Middleware that activates the user's timezone based on a cookie.

    The cookie 'user_timezone' should contain an IANA timezone name
    (e.g., 'America/New_York', 'Europe/London').
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.COOKIES.get("user_timezone")
        if tzname:
            try:
                timezone.activate(zoneinfo.ZoneInfo(tzname))
            except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                # Invalid timezone, fall back to UTC
                timezone.deactivate()
        else:
            timezone.deactivate()

        response = self.get_response(request)
        return response
