import datetime
import json
import random

from django import http
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy, reverse
from django.utils.datastructures import MultiValueDictKeyError
from django.views.generic import (
    DetailView,
    ListView,
    CreateView,
    DeleteView,
    FormView,
    UpdateView,
    TemplateView,
)

from lms.errors import (
    MaxLoansError,
    ObjectExistsError,
    APINotFoundError,
    MaxRenewalsError,
    BookUnavailableError,
)
from lms.forms import LibraryUserCreationForm, LibraryUserProfileForm
from lms.models import BookCopy, Book, Author, LibraryUser, Loan, Reservation
from lms.permissions import KioskPermissionMixin


############
# Kiosk
############
class KioskHome(KioskPermissionMixin, LoginRequiredMixin, ListView):
    """Render the kiosk home page, providing a list of the user's loans to the
    template."""

    template_name = "lms/kiosk/home.html"
    context_object_name = "loans"

    def get_queryset(self):
        # send a QuerySet of the user's loans to the template as 'loans'
        return self.request.user.loans.all()

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        data["accession_code_lookup"] = json.dumps(
            {loan.book.accession_code: str(loan.id) for loan in data["loans"]}
        )
        return data


# noinspection PyAttributeOutsideInit
class KioskTakeOut(KioskPermissionMixin, LoginRequiredMixin, CreateView):
    """Render the kiosk take out page and accept form submissions, ensuring that the
    accession code entered is valid and not currently on loan/reserved."""

    model = Loan
    template_name = "lms/kiosk/take_out.html"
    # 'book' is a BookCopy, so this will generate an accession code-accepting form field
    fields = ["book"]
    success_url = reverse_lazy("kiosk_take_out")

    def form_valid(self, form):
        """Validate the form data, ensuring the user hasn't reached their loan limit
        and the book is available, then show useful success/error message."""
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        try:
            self.object.save()
        except MaxLoansError:
            messages.error(
                self.request,
                "You already have the maximum number of loans allowed. Please return "
                "a book before trying again.",
            )
        except BookUnavailableError:
            messages.error(
                self.request, "This book is either already on loan or reserved."
            )
        else:
            messages.success(
                self.request,
                # JSON data will be rendered by Alpine in the template
                json.dumps(
                    {
                        "due_date": self.object.due_date.strftime("%A %#d %B %Y"),
                        "title": self.object.book.book.title,
                        "renewals_allowed": self.request.user.renewal_limit,
                    }
                ),
                extra_tags="loan_confirmation",
            )
        return http.HttpResponseRedirect(self.get_success_url())


class KioskReturn(
    KioskPermissionMixin, LoginRequiredMixin, SuccessMessageMixin, DeleteView
):
    """Render the kiosk return confirmation page and accept confirmation submissions,
    ensuring that the accession code entered is valid and currently on loan to the
    user."""

    model = Loan
    template_name = "lms/kiosk/return.html"
    success_url = reverse_lazy("kiosk_home")
    context_object_name = "loan"
    success_message = "Book successfully returned. Thanks for using our library!"

    def get_queryset(self):
        return self.request.user.loans.all()


@staff_member_required
def activate_kiosk(request):
    """Sets a cookie authorising the web browser to access the kiosk pages during the
    current day, logging the current user out and redirecting them to the kiosk page."""
    res = http.HttpResponseRedirect(f"{reverse('logout')}?next={reverse('kiosk_home')}")
    midnight = datetime.datetime.combine(
        datetime.date.today() + datetime.timedelta(days=1), datetime.time.min
    )
    res.set_signed_cookie(
        key="kiosk_activated",
        value=str(datetime.date.today()),
        expires=midnight,
        httponly=True,
    )
    messages.success(
        request, "Kiosk successfully activated on this device until midnight."
    )
    return res


@staff_member_required
def deactivate_kiosk(request):
    """Delete the kiosk activation cookie and redirect the user to the admin site with
    a success message."""
    res = http.HttpResponseRedirect(reverse("admin:lms_book_changelist"))
    res.delete_cookie(key="kiosk_activated")
    messages.success(request, "Kiosk successfully deactivated on this device.")
    return res


############
# Frontend (main)
############
class MainHome(ListView):
    """Render the site's main page, providing the lists of featured books and newly
    added books to be shown on the page."""

    template_name = "lms/main/home.html"
    model = Book

    def get_queryset(self):
        # get the books marked as featured in the admin
        return self.model.objects.filter(featured=True)

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        # order the books by most recently created, then get the first 10
        data["newly_added"] = Book.objects.all().order_by("-created")[:10]
        return data


class SearchView(ListView):
    """Render the search results template with either book or author objects
    (depending on the path the request is sent to) and showing objects that
    match the results of a search using the query specified."""

    template_name = "lms/main/search_results.html"
    model = Book

    def get_queryset(self):
        # ensure query was passed in GET parameters
        try:
            query = self.request.GET["q"]
        except MultiValueDictKeyError:
            return None
        # return either book or author objects depending on the second path segment
        if self.kwargs["type"] == "books":
            books = Book.objects.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(isbn=query)
                | Q(edition_id__iexact=query)
                | Q(work_id__iexact=query)
            )
            return books
        elif self.kwargs["type"] == "authors":
            authors = Author.objects.filter(name__icontains=query)
            return authors


class UserProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Render the site's main page, allowing them to view/update their account
    information and view loan/reservation information"""

    template_name = "lms/main/user_profile.html"
    form_class = LibraryUserProfileForm
    success_url = reverse_lazy("user_profile")
    success_message = "Account information updated"

    def get_object(self, **kwargs):
        # provide the currently logged in user as the object to be updated
        return self.request.user

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        # get all the user's reservations that have copies assigned to them ordered by
        # how long they've been ready
        data["available_reservations"] = self.request.user.reservations.filter(
            copy__isnull=False
        ).order_by("ready_since")
        # get all the user's reservations that DO NOT have copies assigned to them
        data["not_available_reservations"] = self.request.user.reservations.filter(
            copy__isnull=True
        )
        return data


class BookDetailView(DetailView):
    """Render a detail view for book objects, displaying their covers, IDs, titles,
    authors, copies, other editions, and books by the same author"""

    template_name = "lms/main/view_book.html"
    model = Book
    slug_field = "edition_id"
    slug_url_kwarg = "edition_id"

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        # get a list of the IDs of every author of the book
        authors = [author.id for author in self.object.authors.all()]
        # get a list of books that were written by at least one of the authors from
        # the 'authors' list, prioritising the ones with cover images for aesthetic
        # purposes
        data["other_author_books"] = (
            Book.objects.filter(authors__in=authors)
            .exclude(work_id=self.object.work_id)
            .order_by("cover_file")
            .reverse()
        )
        return data


class AuthorDetailView(DetailView):
    """Render a detail view for author objects, displaying a list of their books,
    alongside accompanying information, in either card or list format."""

    template_name = "lms/main/view_author.html"
    model = Author
    slug_field = "id"
    slug_url_kwarg = "author_id"


class ReserveView(LoginRequiredMixin, CreateView):
    """Render information about a book with the option to confirm making a
    reservation before saving the reservation to the database and sending the user to
    their profile page to view information about it."""

    template_name = "lms/main/reserve_book.html"
    model = Reservation
    fields = []
    success_url = reverse_lazy("user_profile")

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        # gets the book being reserved so the user can confirm it is correct
        data["book"] = Book.objects.get(edition_id=self.kwargs["edition_id"])
        return data

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # get the user and book from the request/url
        self.object.user = self.request.user
        self.object.book = Book.objects.get(edition_id=self.kwargs["edition_id"])

        # attempt to assign a copy to the reservation object and save it
        ready_now = self.object.assign_book_copy()
        self.object.save()

        # sends JSON data of the title of the book, if it is ready now, and if not
        # when the earliest due date for one of the copies is, which Alpine will then
        # render into a message on the frontend
        messages.success(
            self.request,
            json.dumps(
                {
                    "title": self.object.book.title,
                    "ready_now": ready_now,
                    "earliest_date_ready": self.object.book.copy_next_available.strftime(
                        "%A %#d %B %Y"
                    )
                    if not ready_now
                    else None,
                }
            ),
            extra_tags="reservation_confirmation",
        )
        return http.HttpResponseRedirect(self.get_success_url())


class RenewalView(LoginRequiredMixin, UpdateView):
    """Doesn't render a template, instead providing an endpoint for other pages to
    send loan renewal requests to, which it will carry out (as long as the
    permissions are correct)."""

    model = Loan
    fields = []
    success_url = reverse_lazy("user_profile")

    def get_queryset(self):
        # ensures that only user's can only renew their own loans
        return self.request.user.loans.all()

    def form_valid(self, form):
        self.object = form.save(commit=False)
        try:
            self.object.renew()
        # raised if the user has exceeded their renewal limit for this loan
        except MaxRenewalsError:
            messages.error(
                self.request,
                f"{self.object.book.book.title} ({self.object.book.accession_code}) "
                f"has already been renewed the maximum number of times",
            )
        else:
            self.object.save()
            # Alpine renders the JSON data on the frontend
            messages.success(
                self.request,
                json.dumps(
                    {
                        "due_date": self.object.due_date.strftime("%A %#d %B %Y"),
                        "title": self.object.book.book.title,
                        "renewals_used": self.object.renewals,
                        "renewals_allowed": self.request.user.renewal_limit,
                    }
                ),
                extra_tags="renewal_confirmation",
            )
        return http.HttpResponseRedirect(self.get_success_url())


############
# Backend (admin)
############
@staff_member_required
@permission_required("lms.book.add", login_url=reverse_lazy("admin:login"))
def import_book(request):
    """Renders the book import template on a GET request. On POST request, deserialises
    JSON in POST request body and splits multiple accession code objects into multiple
    single accession code objects, then creates books, and if necessary book copies from
    these ISBNS (and accession codes) using the 'from_isbn' class methods on these model
    classes."""
    if request.method == "POST":
        try:
            # deserialise the JSON from the POST body and extract the useful fields
            data = json.loads(request.body)
            fields = data["fields"]
            includes_accessions = data["include_accessions"]

            # split multi-accession code objects into multiple single accession code
            # objects if required (only applicable when creating book copies)
            if includes_accessions:
                new_fields = []
                for field in fields:
                    accessions = field["accession"].split(",")
                    for accession in accessions:
                        new_fields.append(
                            {
                                "isbn": field["isbn"],
                                "accession": accession.strip(),
                                "error": field["error"],
                            }
                        )
                fields = new_fields

            # initialise results variables to be passed back to frontend in response
            errors = []
            successes = []
            accessions_in_successes = False

            # attempt to import a book, and book copy if accession are included, from
            # each provided ISBN (/accession code), saving any errors to the object
            # and putting it in the errors list while putting any successes
            # in the successes list
            for field in fields:
                try:
                    if includes_accessions:
                        book_copy = BookCopy.from_isbn(
                            field["isbn"], field["accession"]
                        )
                    else:
                        book = Book.from_isbn(field["isbn"])
                except ObjectExistsError:
                    field["error"] = "ObjectExistsError"
                    errors.append(field)
                except APINotFoundError:
                    field["error"] = "APINotFoundError"
                    errors.append(field)
                else:
                    # place some basic information from each imported book into a plain
                    # python dictionary to be serialised into json
                    if includes_accessions:
                        accessions_in_successes = True
                        successes.append(
                            {
                                "isbn": book_copy.book.isbn,
                                "edition_id": book_copy.book.edition_id,
                                "title": book_copy.book.title,
                                "authors": book_copy.book.authors_name_string,
                                "accession": book_copy.accession_code,
                                "admin_url": reverse(
                                    "admin:lms_book_change",
                                    args=(book_copy.book.pk,),
                                ),
                                "site_url": book_copy.book.get_absolute_url(),
                            }
                        )
                    else:
                        successes.append(
                            {
                                "isbn": book.isbn,
                                "edition_id": book.edition_id,
                                "title": book.title,
                                "authors": book.authors_name_string,
                                "admin_url": reverse(
                                    "admin:lms_book_change",
                                    args=(book.pk,),
                                ),
                                "site_url": book.get_absolute_url(),
                            }
                        )

            # return json to the javascript component on the frontend
            return JsonResponse(
                {
                    "errors": errors,
                    "successes": {
                        "book_data": successes,
                        "includes_accessions": accessions_in_successes,
                    },
                }
            )

        except KeyError as err:  # will happen if required post data not sent
            return JsonResponse({"server_error": True})
    else:
        # render the template
        return render(request, "lms/admin/import_book.html")


class AccessionCodeGenerationView(TemplateView):
    """Renders a template capable of generating any number of accession codes with
    accompanying QR codes, ready to be printed. Defaults to ensuring that only
    non-existent accession codes can be generated by providing the highest existing
    accession code plus one as starting accession code."""

    template_name = "lms/admin/accession_code_sheet.html"

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        # accession codes greater than the current highest one are guaranteed to be
        # unused
        highest_accession_code = BookCopy.objects.order_by("-accession_code").first()
        data["starting_accession_code"] = highest_accession_code.accession_code + 1
        return data


############
# Auth
############
class UserRegistrationView(FormView):
    """Allow users to register using a custom form to bypass Django's default
    registration form that only allows entry of username and password. Provides
    custom submission logic to automatically generate a library card number as the
    username, ensuring that the library card number is unique to that user."""

    form_class = LibraryUserCreationForm
    template_name = "lms/main/user_registration.html"
    success_url = reverse_lazy("user_profile")

    def form_valid(self, form):
        # generate library card number (username) while making sure it doesn't
        # already exist
        while True:
            username = random.randint(1000000000, 9999999999)
            if LibraryUser.objects.filter(username=username).exists():
                continue
            break

        # create user object from form data and generated username
        user = LibraryUser.objects.create_user(
            username,
            form.cleaned_data.get("email"),
            form.cleaned_data.get("password1"),
        )

        # add extra user information and save
        user.first_name = form.cleaned_data.get("first_name")
        user.last_name = form.cleaned_data.get("last_name")
        user.save()

        # logs the user in, showing a success message
        login(self.request, user)
        messages.success(
            self.request,
            "Welcome to the library! Make sure to scroll down to the "
            "'Account information' section to view your library card "
            "number, which you will need to log in in the the future.",
        )

        # redirect the user to the success url (the profile page)
        return http.HttpResponseRedirect(self.get_success_url())
