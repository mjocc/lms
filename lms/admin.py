from datetime import date, timedelta
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from csvexport.actions import csvexport
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.files import File
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import ngettext
from django_object_actions import DjangoObjectActions, action

from .errors import MaxLoansError, BookUnavailableError, MaxRenewalsError
from .models import LibraryUser, Author, Book, BookCopy, Loan, Reservation, HistoryLoan


class BookCopyInline(admin.TabularInline):
    """Inline book copy admin inline allowing information on existing book copies to
    be displayed inline."""

    model = BookCopy
    extra = 0


class LoanInline(admin.StackedInline):
    """Inline loan admin allowing info on a single loan (including due dates/renewals)
    to be viewed and loans managed."""

    model = Loan
    autocomplete_fields = ["user"]
    fields = ["user", "loan_date", "renewal_date", "renewals", "due_date"]
    readonly_fields = ["loan_date", "due_date", "renewals"]
    extra = 0

    @admin.display
    def due_date(self, obj):
        return obj.due_date.strftime("%d %b %Y")


class HistoryLoanInline(admin.StackedInline):
    """Inline history loan admin allowing the loan history of a book copy to be
    displayed inline on its model admin."""

    model = HistoryLoan
    fields = ["user", "loan_date", "returned_date"]
    readonly_fields = ["user", "loan_date", "returned_date"]
    extra = 0


class ReservationInline(admin.StackedInline):
    """Inline reservation admin allowing information on a book outstanding reservations
    and a book copy's existing reservation to be shown."""

    model = Reservation
    autocomplete_fields = ["user"]
    fields = ["user", "ready_since", "off_shelves"]
    extra = 0


class ReservationExpiredListFilter(admin.SimpleListFilter):
    """Custom list filter for reservation admin changelist to check if the reservations
    are expired or not."""

    # human-readable title which will be displayed in the
    # right admin sidebar just above the filter options
    title = "reservation expired"

    # parameter for the filter that will be used in the URL query
    parameter_name = "expired"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ("1", "Expired"),
            ("0", "Not expired"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either 'true' or 'false')
        # to decide how to filter the queryset.
        if self.value() == "1":
            return queryset.filter(
                ready_since__isnull=False,
                ready_since__lte=(date.today() - timedelta(days=7)),
            )
        if self.value() == "0":
            return queryset.filter(
                Q(ready_since__isnull=True)
                | Q(ready_since__gt=(date.today() - timedelta(days=7)))
            )


@admin.register(Book)
class BookAdmin(DjangoObjectActions, admin.ModelAdmin):
    """Book admin allowing management of stock, kiosk system, home page,
    data import and filtering of stock items from the changelist, as well as
    data editing, cover image management, book copy management, and reservation
    management from the detail view."""

    actions = ["download_image", "add_featured", "remove_featured", csvexport]
    search_fields = ["isbn__exact", "edition_id__iexact", "work_id__iexact", "title"]
    autocomplete_fields = ["authors"]
    list_display = [
        "isbn",
        "title",
        "authors_name_string",
        "date_published",
        "has_cover",
        "num_copies",
        "featured",
    ]
    list_filter = [
        ("cover_url", admin.EmptyFieldListFilter),
        ("date_published", admin.EmptyFieldListFilter),
        "featured",
    ]
    changelist_actions = ["import_book", "activate_kiosk"]
    change_actions = ["download_single_image", "search_on_amazon"]
    inlines = [BookCopyInline, ReservationInline]

    @admin.display(
        boolean=True,
        description="Has cover",
    )
    def has_cover(self, obj):
        return bool(obj.cover_file)

    @admin.display(description="Num. copies available")
    def num_copies(self, obj):
        return f"{obj.num_copies_available} / {obj.copies.count()}"

    @admin.action(description="Download image(s) from cover_url")
    def download_image(self, request, queryset):
        """Download image from the url in the selected books' cover_url fields and
        store the file in their cover_file fields."""

        # initialise image download counter
        images_downloaded = 0

        # loop through every selected book, check if it has a cover_url but not
        # a downloaded cover_file, and if so download the image into a temporary file
        # and save it to the cover_file field
        for obj in queryset:
            if obj.cover_url and not obj.cover_file:
                img_temp = NamedTemporaryFile(delete=True)
                img_temp.write(urlopen(obj.cover_url).read())
                img_temp.flush()
                obj.cover_file.save(obj.pk, File(img_temp))
                images_downloaded += 1

        # send a success message detailing how many images were successfully downloaded
        self.message_user(
            request,
            ngettext(
                "%d image was successfully downloaded.",
                "%d images were successfully downloaded.",
                images_downloaded,
            )
            % images_downloaded,
            messages.SUCCESS,
        )

    @admin.action(description="Add book(s) to featured")
    def add_featured(self, request, queryset):
        """Add selected books to the featured list on the home page."""
        queryset.update(featured=True)
        self.message_user(request, "Book(s) added to featured", messages.SUCCESS)

    @admin.action(description="Remove book(s) from featured")
    def remove_featured(self, request, queryset):
        """Remove selected books from the featured list on the home page."""
        queryset.update(featured=False)
        self.message_user(request, "Book(s) removed from featured", messages.SUCCESS)

    @action(
        label="Download cover_url image",
        description="Download image from cover_url field, overwriting current "
        "cover_file if necessary",
    )
    def download_single_image(self, request, obj):
        """Download image from the url in the current book's cover_url field and
        store the file in its cover_file field (from the detail page)."""

        # check if the book has a cover-Url, and if so download the
        # image into a temporary file and save it to the cover_file field
        if obj.cover_url:
            img_temp = NamedTemporaryFile(delete=True)
            img_temp.write(urlopen(obj.cover_url).read())
            img_temp.flush()
            obj.cover_file.save(obj.pk, File(img_temp))

            self.message_user(
                request,
                "Image was successfully downloaded.",
                messages.SUCCESS,
            )

    @action(
        label="Search on Amazon",
        description="Search ISBN on Amazon to get book information",
    )
    def search_on_amazon(self, request, obj):
        """Search the book on amazon so as to easily find metadata, cover image, etc."""
        return HttpResponseRedirect(f"https://www.amazon.co.uk/s?k={obj.isbn}")

    @action(label="Import book", description="Import book from ISBN")
    def import_book(self, request, queryset):
        """Open the book import page."""
        return HttpResponseRedirect(reverse("import_book"))

    @action(
        label="Activate kiosk",
        description="Activate this device as a kiosk for the day",
    )
    def activate_kiosk(self, request, queryset):
        """Activate the kiosk and log this user out by redirecting them to the
        kiosk activation view."""
        return HttpResponseRedirect(reverse("activate_kiosk"))


@admin.register(BookCopy)
class BookCopyAdmin(DjangoObjectActions, admin.ModelAdmin):
    """Book copy admin allowing viewing info on and filtering of stock items from
    the changelist, as well as data editing, current loan management, loan history
    information, and reservation management from the detail view."""

    search_fields = [
        "book__title__icontains",
        "book__isbn__exact",
        "book__edition_id__exact",
        "accession_code__iexact",
    ]
    autocomplete_fields = ["book"]
    list_display = [
        "accession_code",
        "book_title",
        "book_isbn",
        "on_loan",
        "reserved",
        "due_date",
    ]
    list_filter = [("current_loan", admin.EmptyFieldListFilter)]
    actions = [csvexport]
    change_actions = ["renew_loan", "force_loan_renewal"]
    inlines = [LoanInline, HistoryLoanInline, ReservationInline]

    @admin.display(ordering="book__title")
    def book_title(self, obj):
        return obj.book.title

    @admin.display(ordering="book__isbn")
    def book_isbn(self, obj):
        return obj.book.isbn

    @admin.display(ordering="current_loan__due_date")
    def due_date(self, obj):
        if obj.unavailable:
            return obj.due_date
        return None

    @admin.display(boolean=True)
    def on_loan(self, obj):
        return hasattr(obj, "current_loan")

    @admin.display(boolean=True)
    def reserved(self, obj):
        return hasattr(obj, "reservation")

    @action
    def renew_loan(self, request, obj, force=False):
        """Renew a loan using the method built in to the loan model class, which
        checks if the user has hit their loan limit. If they have, a loan renewal
        can be forced by passing a True value to the force argument."""

        # Ensure the book is actually on loan, showing an error message if not
        if hasattr(obj, "current_loan"):
            # Attempt to renew it, checking for if the book has hit the max number
            # of renewals and then either showing an error message or saving the
            # changes and showing a success message
            try:
                obj.current_loan.renew(force=force)
            except MaxRenewalsError:
                self.message_user(
                    request,
                    "Loan has been renewed the maximum number of times. Use 'Force "
                    "loan renewal' to override.",
                    messages.WARNING,
                )
            else:
                obj.current_loan.save()
                self.message_user(
                    request,
                    f"Loan renewed successfully. {obj.current_loan.renewals} out of "
                    f"{obj.current_loan.user.renewal_limit} renewals used. "
                    f"Now due {obj.current_loan.due_date}.",
                    messages.SUCCESS,
                )
        else:
            self.message_user(
                request,
                "Book copy isn't on loan, so cannot be renewed.",
                messages.WARNING,
            )

    @action(
        description="Will force loan renewal, going over renewal limit if necessary"
    )
    def force_loan_renewal(self, *args):
        self.renew_loan(*args, force=True)


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    """Author admin allowing viewing info on and filtering of stock items from
    the changelist, as well as basic data editing from the detail view."""

    actions = [csvexport]
    search_fields = ["id__iexact", "name"]
    list_display = ["id", "name", "num_titles"]

    @admin.display(description="Num. titles")
    def num_titles(self, obj):
        return obj.books.count()


@admin.register(Reservation)
class ReservationAdmin(DjangoObjectActions, admin.ModelAdmin):
    """Reservation admin allowing management of reservations, filtering of existing
    reservations, and management of book locations (i.e. on the shelves or not) from
    the changelist, as well as data editing, assigning available book copies, and
    turning a reservation into a loan when a user comes to collect it."""

    actions = ["mark_off_shelves", csvexport]
    search_fields = [
        "id__iexact",
        "book__title__icontains",
        "user__last_name__icontains",
        "user__first_name__icontains",
        "user__username__iexact",
    ]
    autocomplete_fields = ["user", "book", "copy"]
    list_display = [
        "book_title",
        "user_full_name",
        "has_copy",
        "accession_code",
        "ready_since",
        "off_shelves",
        "expired",
    ]
    change_actions = ["assign_book_copy", "turn_into_loan"]
    list_filter = ["off_shelves", ReservationExpiredListFilter]

    @admin.display(ordering="copy__accession_code", description="copy accession")
    def accession_code(self, obj):
        if not obj.needs_copy:
            return obj.copy.accession_code

    @admin.display(ordering="book__title")
    def book_title(self, obj):
        return obj.book.title

    @admin.display(ordering="user__last_name")
    def user_full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(
        boolean=True,
        description="Has copy",
    )
    def has_copy(self, obj):
        return not obj.needs_copy

    @admin.display(boolean=True)
    def expired(self, obj):
        return obj.expired

    @admin.action(description="Mark book(s) as having been taken off the shelves")
    def mark_off_shelves(self, request, queryset):
        """Allow librarians to keep track of when they have taken books off the
        shelves through an object action that can be called on any selected
        objects."""
        queryset.update(off_shelves=True)
        self.message_user(
            request,
            "Books marked as off the shelves successfully.",
            messages.SUCCESS,
        )

    @action(
        label="Assign book copy",
        description="Assign book copy to reservation if it doesn't already have one",
    )
    def assign_book_copy(self, request, obj):
        """Checks if there is a book copy available and that the selected reservation
        doesn't already have one, then assigns that copy to it. Shouldn't generally have
        to be used, as reservations are automatically assigned book copies if available
        when they are created and a check if performed every time a book is returned to
        see if there are any outstanding reservations for it."""
        # calls the function defined on the model class to carry out the logic
        # described above
        result = obj.assign_book_copy()

        # checks the result of the above functions call and sends a sensible status
        # message to let the librarian know what has happened
        if result is not None:
            obj.save()
            if result:
                self.message_user(
                    request,
                    "Copy successfully assigned.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request, "No copies available for reservation.", messages.WARNING
                )
        else:
            self.message_user(
                request, "Reservation already has copy.", messages.WARNING
            )

    @action(
        label="Turn into loan",
        description="Loan the reserved copy out to the user it was reserved to, "
        "deleting the reservation",
    )
    def turn_into_loan(self, request, obj):
        """Allows the reservation to easily be turned into a loan by a librarian when
        the user comes to collect the book (otherwise the reservation would have to
        be deleted and then the loan created because the reservation marks the book
        copy as being generally inaccessible for loans)."""

        # create a loan from the reservation and attempt to save it, displaying an error
        # message if the user has already reached their loan limit or if there has been
        # an error and the book is somehow already on loan/reserved by someone else
        loan = Loan(user=obj.user, book=obj.copy)
        try:
            loan.save(ignore_unavailable=True)
        except MaxLoansError:
            self.message_user(request, "Max loans already reached.", messages.WARNING)
        except BookUnavailableError:  # should never happen but included to be safe
            self.message_user(
                request,
                "This book is either already on loan or reserved.",
                messages.WARNING,
            )
        else:
            # if there wasn't a problem with saving the loan, deletes the reservation
            # and shows a success message before redirecting to the admin page for the
            # book copy that was just created (which will show the loan information)
            obj.delete()
            self.message_user(
                request,
                f"Reservation turned into loan successfully. Book due back "
                f"{loan.due_date.strftime('%d %b %Y')}.",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(
                reverse("admin:lms_bookcopy_change", args=(loan.book.pk,))
            )


# register the user model with Django's built-in model admin that allows passwords to
# be reset, account information viewed in a sensible manner, etc.
admin.site.register(LibraryUser, UserAdmin)

# set basic customisation/branding options for the admin
admin.site.site_header = "Librarian/Volunteer System"
admin.site.site_title = "LMS"
admin.site.index_title = "Management"
