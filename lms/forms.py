from django.contrib.auth.forms import UserCreationForm
from django.forms import ModelForm

from lms.models import LibraryUser


class LibraryUserCreationForm(UserCreationForm):
    """Registration form for users, allowing them to enter their name and email in
    addition to the default registration forms password and password confirmation.
    Account creation is manually processed in the view in order to generate a unique
    library card number for each user."""

    class Meta(UserCreationForm.Meta):
        model = LibraryUser
        fields = (
            "first_name",
            "last_name",
            "email",
        )


class LibraryUserProfileForm(ModelForm):
    """Form for user profile page allowing them to update their basic account
    information. Usernames cannot be updated by users themselves as they are unique
    library card numbers and PIN updates are handled through a separate flow ensuring
    higher security for users' accounts."""

    class Meta:
        model = LibraryUser
        fields = (
            "first_name",
            "last_name",
            "email",
        )
