from django.contrib.auth.forms import UserCreationForm
from django.forms import ModelForm

from lms.models import LibraryUser


class LibraryUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = LibraryUser
        fields = (
            "first_name",
            "last_name",
            "email",
        )


class LibraryUserProfileForm(ModelForm):
    class Meta:
        model = LibraryUser
        fields = (
            "first_name",
            "last_name",
            "email",
        )
