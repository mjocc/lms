import json
import random

from django import http
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    DetailView,
    ListView,
    CreateView,
    DeleteView,
    TemplateView,
    FormView,
    UpdateView,
)
from rest_framework import viewsets
from rest_framework_simplejwt.views import TokenObtainSlidingView

from lms.errors import MaxLoansError, ObjectExistsError, APINotFoundError
from lms.forms import LibraryUserCreationForm, LibraryUserProfileForm
from lms.models import BookCopy, Book, Author, LibraryUser, Loan
from lms.permissions import group_required
from lms.serializers import (
    LibraryUserSerializer,
    AuthorSerializer,
    BookSerializer,
    LoanSerializer,
    LibraryTokenObtainSlidingSerializer,
)


class TESTING(ListView):
    model = BookCopy
    template_name = "lms/TESTING.html"
    context_object_name = "books"


############
# Kiosk
############
class KioskHome(LoginRequiredMixin, ListView):
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


class KioskTakeOut(LoginRequiredMixin, CreateView):
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
        else:
            messages.success(
                self.request,
                json.dumps(
                    {
                        "due_date": self.object.due_date.strftime("%A %d %B %Y"),
                        "title": self.object.book.book.title,
                        "renewals_allowed": self.request.user.renewal_limit,
                    }
                ),
                extra_tags="loan_confirmation",
            )
        return http.HttpResponseRedirect(self.get_success_url())


class KioskReturn(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Loan
    template_name = "lms/kiosk/return.html"
    success_url = reverse_lazy("kiosk_home")
    context_object_name = "loan"
    success_message = "Book successfully returned. Thanks for using our library!"

    def get_queryset(self):
        return self.request.user.loans.all()


############
# Frontend (main)
############
class MainHome(TemplateView):
    template_name = "lms/main/home.html"
    # TODO: finish main home view


class UserProfileView(LoginRequiredMixin, UpdateView):
    template_name = "lms/main/user_profile.html"
    form_class = LibraryUserProfileForm
    success_url = reverse_lazy("user_profile")

    def get_object(self, **kwargs):
        return self.request.user

############
# Backend (admin)
############
@login_required
@group_required("Volunteer")
def import_book(request):
    # TODO: need form verification, error messages, etc. + PERMISSIONS
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
                                "title": book_copy.book.title,
                                "authors": book_copy.book.authors_name_string,
                                "accession": book_copy.accession_code,
                                "admin_url": reverse(
                                    "admin:lms_book_change",
                                    args=(book_copy.book.pk,),
                                ),
                            }
                        )
                    else:
                        successes.append(
                            {
                                "isbn": book.isbn,
                                "title": book.title,
                                "authors": book.authors_name_string,
                                "admin_url": reverse(
                                    "admin:lms_book_change",
                                    args=(book.pk,),
                                ),
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
            # TODO: implement this error
            return JsonResponse({"message": "ERROR NEEDS TO BE PROPERLY IMPLEMENTED"})
    else:
        return render(request, "lms/admin/import_book.html")


class BookDetailView(DetailView):
    template_name = "lms/view_book.html"
    model = Book
    slug_field = "edition_id"
    slug_url_kwarg = "edition_id"


class AuthorDetailView(DetailView):
    template_name = "lms/view_author.html"
    model = Author
    slug_field = "id"
    slug_url_kwarg = "author_id"


############
# Auth
############
class UserRegistrationView(FormView):
    form_class = LibraryUserCreationForm
    template_name = "lms/user_registration.html"
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


############
# API
############
class LibraryUserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows library users to be viewed or edited.
    """

    queryset = LibraryUser.objects.all()
    serializer_class = LibraryUserSerializer

    def create(self, validated_data, **kwargs):
        library_user = LibraryUser.objects.create_user(**validated_data)
        return library_user


class AuthorViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows authors to be viewed or edited.
    """

    queryset = Author.objects.all()
    serializer_class = AuthorSerializer


class BookViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows books to be viewed or edited.
    """

    queryset = Book.objects.all()
    serializer_class = BookSerializer


class LoanViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows loans to be viewed or edited.
    """

    queryset = Loan.objects.all()
    serializer_class = LoanSerializer


class LibraryTokenObtainSlidingView(TokenObtainSlidingView):
    serializer_class = LibraryTokenObtainSlidingSerializer
