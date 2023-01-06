from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group

# Basic library users will have no group
# Librarians will be superusers (`python manage.py createsuperuser`)

volunteer_group, _ = Group.objects.get_or_create(name="Volunteer")
volunteer_group.permissions.add()
#TODO: work out what permission to put here


def group_required(*group_names):
    """Requires user membership in at least one of the groups passed in."""
    def in_groups(u):
        if u.is_authenticated:
            if bool(u.groups.filter(name__in=group_names)) | u.is_superuser:
                return True
        return False

    return user_passes_test(in_groups, login_url='403')