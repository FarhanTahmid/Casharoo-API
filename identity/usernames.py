"""
Usernames are unique case-insensitively. The default one is the part of the
email before the @; when that is taken it gets 4 random digits on the end.
"""
import re
import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

MAX_LENGTH = 150
SUFFIX_DIGITS = 4
ATTEMPTS = 20
# No @ or whitespace, so the login box can tell a username from an email
USERNAME_RE = re.compile(r'^[\w.+-]+$')


def base_from_email(email):
    return email.split('@')[0][:MAX_LENGTH - SUFFIX_DIGITS]


def with_suffix(base):
    return f'{base[:MAX_LENGTH - SUFFIX_DIGITS]}{secrets.randbelow(10 ** SUFFIX_DIGITS):0{SUFFIX_DIGITS}d}'


def is_taken(username, exclude_user=None):
    users = get_user_model().objects.filter(username__iexact=username)
    if exclude_user is not None and exclude_user.pk:
        users = users.exclude(pk=exclude_user.pk)
    return users.exists()


def generate_unique_username(email, exclude_user=None):
    base = base_from_email(email) or 'user'
    if not is_taken(base, exclude_user):
        return base
    for _ in range(ATTEMPTS):
        candidate = with_suffix(base)
        if not is_taken(candidate, exclude_user):
            return candidate
    raise RuntimeError(f'Could not find a free username for {base!r}')


def suggestions(username, count=3):
    """Free variants of a taken username"""
    found = []
    for _ in range(ATTEMPTS):
        candidate = with_suffix(username)
        if candidate not in found and not is_taken(candidate):
            found.append(candidate)
            if len(found) == count:
                break
    return found


def validate_username(value, user):
    """Rules for a username the user picks. Returns the cleaned value"""
    value = (value or '').strip()
    if not value or len(value) > MAX_LENGTH or not USERNAME_RE.match(value):
        raise ValidationError(
            'Use letters, numbers and . _ + - only, up to 150 characters.', code='invalid'
        )
    if is_taken(value, exclude_user=user):
        raise ValidationError('This username is already taken.', code='taken')
    return value
