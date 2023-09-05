from django.db.models.signals import post_delete
from django.dispatch import receiver

from lms.models import Reservation


@receiver(post_delete, sender=Reservation)
def handle_reservation_delete(sender, instance, **kwargs):
    """Assign book copy to any outstanding reservations when a reservation is
    deleted."""

    # get reservation that has been waiting the longest for a book (the 'first')
    reservation = Reservation.objects.filter(copy__isnull=True,
                                             book=instance.book).first()

    # manually assign the book copy of the reservation that was just deleted
    # to an outstanding reservation if found and save it
    if reservation:
        reservation.assign_book_copy(copy=instance.copy, email_on_success=True)
        reservation.save()
