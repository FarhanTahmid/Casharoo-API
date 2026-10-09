from allauth.account.adapter import DefaultAccountAdapter

from .usernames import generate_unique_username


class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        # Email sign-up and Google sign-in both end up here
        if not user.username:
            user.username = generate_unique_username(user.email)
