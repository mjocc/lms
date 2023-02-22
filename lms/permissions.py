from datetime import date

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

# Basic library users will have no group
# Volunteers will be staff and have the Volunteer group
# Librarians will be superusers (`python manage.py createsuperuser`)

volunteer_group, _ = Group.objects.get_or_create(name="Volunteer")


# volunteer_group.permissions.add("lms.author.add")
# volunteer_group.permissions.add("lms.author.change")
# volunteer_group.permissions.add("lms.author.view")
# volunteer_group.permissions.add("lms.book.add")
# volunteer_group.permissions.add("lms.book.change")
# volunteer_group.permissions.add("lms.book.view")
# volunteer_group.permissions.add("lms.book_copy.add")
# volunteer_group.permissions.add("lms.book_copy.change")
# volunteer_group.permissions.add("lms.book_copy.delete")
# volunteer_group.permissions.add("lms.book_copy.view")
# volunteer_group.permissions.add("lms.history.view")
# volunteer_group.permissions.add("lms.loan.add")
# volunteer_group.permissions.add("lms.loan.change")
# volunteer_group.permissions.add("lms.loan.delete")
# volunteer_group.permissions.add("lms.loan.view")
# volunteer_group.permissions.add("lms.reservation.add")
# volunteer_group.permissions.add("lms.reservation.change")
# volunteer_group.permissions.add("lms.reservation.delete")
# volunteer_group.permissions.add("lms.reservation.view")


class ViewPermissionsMixin(object):
    """Base class for all custom permission mixins to inherit from"""

    def has_permissions(self):
        return True

    def dispatch(self, request, *args, **kwargs):
        if not self.has_permissions():
            raise PermissionDenied
        return super(ViewPermissionsMixin, self).dispatch(request, *args, **kwargs)


class KioskPermissionMixin(ViewPermissionsMixin):
    def has_permissions(self):
        return self.request.get_signed_cookie(
            key="kiosk_activated", default=None
        ) == str(date.today())
