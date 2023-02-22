import datetime
import json
import random

from django import http
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
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
    template_name = "lms/kiosk/home.html"
    context_object_name = "loans"

    def get_queryset(self):
        return self.request.user.loans.all()

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        data["accession_code_lookup"] = json.dumps(
            {loan.book.accession_code: str(loan.id) for loan in data["loans"]}
        )
        return data


class KioskTakeOut(KioskPermissionMixin, LoginRequiredMixin, CreateView):
    model = Loan
    template_name = "lms/kiosk/take_out.html"
    fields = ["book"]
    success_url = reverse_lazy("kiosk_take_out")

    def form_valid(self, form):
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
    model = Loan
    template_name = "lms/kiosk/return.html"
    success_url = reverse_lazy("kiosk_home")
    context_object_name = "loan"
    success_message = "Book successfully returned. Thanks for using our library!"

    def get_queryset(self):
        return self.request.user.loans.all()


@staff_member_required
def activate_kiosk(request):
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
    res = http.HttpResponseRedirect(reverse("admin:lms_book_changelist"))
    res.delete_cookie(key="kiosk_activated")
    messages.success(request, "Kiosk successfully deactivated on this device.")
    return res


############
# Frontend (main)
############
class MainHome(ListView):
    template_name = "lms/main/home.html"
    model = Book

    def get_queryset(self):
        return self.model.objects.filter(featured=True)

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        data["newly_added"] = Book.objects.all().order_by("-created")[:10]
        return data


class SearchView(ListView):
    template_name = "lms/main/search_results.html"
    model = Book

    def get_queryset(self):
        try:
            query = self.request.GET["q"]
        except MultiValueDictKeyError:
            return None
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
    template_name = "lms/main/user_profile.html"
    form_class = LibraryUserProfileForm
    success_url = reverse_lazy("user_profile")
    success_message = "Account information updated"

    def get_object(self, **kwargs):
        return self.request.user

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        data["available_reservations"] = self.request.user.reservations.filter(
            copy__isnull=False
        ).order_by("ready_since")
        data["not_available_reservations"] = self.request.user.reservations.filter(
            copy__isnull=True
        )
        return data


class BookDetailView(DetailView):
    template_name = "lms/main/view_book.html"
    model = Book
    slug_field = "edition_id"
    slug_url_kwarg = "edition_id"

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        authors = [author.id for author in self.object.authors.all()]
        data["other_author_books"] = (
            Book.objects.filter(authors__in=authors)
            .exclude(work_id=self.object.work_id)
            .order_by("cover_file")
            .reverse()
        )
        return data


class AuthorDetailView(DetailView):
    template_name = "lms/main/view_author.html"
    model = Author
    slug_field = "id"
    slug_url_kwarg = "author_id"


class ReserveView(LoginRequiredMixin, CreateView):
    template_name = "lms/main/reserve_book.html"
    model = Reservation
    fields = []
    success_url = reverse_lazy("user_profile")

    def get_context_data(self, *, object_list=None, **kwargs):
        data = super().get_context_data(object_list=object_list, **kwargs)
        data["book"] = Book.objects.get(edition_id=self.kwargs["edition_id"])
        return data

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.book = Book.objects.get(edition_id=self.kwargs["edition_id"])
        ready_now = self.object.assign_book_copy()
        self.object.save()
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
    model = Loan
    fields = []
    success_url = reverse_lazy("user_profile")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        if not self.object.user == self.object.user:
            raise PermissionDenied
        try:
            self.object.renew()
        except MaxRenewalsError:
            messages.error(
                self.request,
                f"{self.object.book.book.title} ({self.object.book.accession_code}) "
                f"has already been renewed the maximum number of times",
            )
        else:
            self.object.save()
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
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            fields = data["fields"]
            includes_accessions = data["include_accessions"]
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

            errors = []
            successes = []
            accessions_in_successes = False
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
        return render(request, "lms/admin/import_book.html")


class AccessionCodeGenerationView(TemplateView):
    template_name = "lms/admin/accession_code_sheet.html"


############
# Auth
############
class UserRegistrationView(FormView):
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

        # redirect the user to the success url (the profile page)
        return http.HttpResponseRedirect(self.get_success_url())
