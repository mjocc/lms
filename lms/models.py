from __future__ import annotations

import datetime
import re
import uuid
from datetime import datetime, date, timedelta
from tempfile import NamedTemporaryFile
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlopen

import datefinder
import requests
from django.contrib import admin
from django.contrib.auth.models import AbstractUser
from django.core.files import File
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import QuerySet
from django.urls import reverse
from isbn_field import ISBNField

from lms.errors import (
    ObjectExistsError,
    APINotFoundError,
    MaxLoansError,
    MaxRenewalsError,
    BookUnavailableError,
)


class LibraryUser(AbstractUser):
    """Extends the generic django user model, adding fields used by the library
    system to manage readers."""

    loans_allowed = models.PositiveSmallIntegerField(
        blank=True,
        default=3,
        help_text="number of books the user is allowed to take out at once",
    )
    loan_length = models.PositiveSmallIntegerField(
        blank=True,
        default=7,
        help_text="number of days that each loan/renewal the user makes is valid for",
    )
    renewal_limit = models.PositiveSmallIntegerField(
        blank=True, default=3, help_text="number of times the user can renew a book"
    )

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"


ol_id_field = dict(
    max_length=20,
    validators=[
        RegexValidator("OL.*", message="Open library IDs should start with `OL`")
    ],
)


class Author(models.Model):
    id = models.CharField(primary_key=True, **ol_id_field)
    name = models.CharField(max_length=50)

    def get_absolute_url(self):
        return reverse("view_author", args=(self.id,))

    def __str__(self):
        return f"{self.name} ({self.id})"


class Book(models.Model):
    isbn = ISBNField(primary_key=True)
    # a certain printing or edition of a text (e.g. the first edition hardback)
    edition_id = models.CharField(**ol_id_field, unique=True)
    # the text itself, including all editions (e.g. 'Hunger Games')
    work_id = models.CharField(**ol_id_field)
    title = models.CharField(max_length=150)
    authors = models.ManyToManyField(Author, related_name="books")
    description = models.TextField(
        blank=True, default="", help_text="description text written in markdown"
    )
    # used to show most recently added books on home page
    created = models.DateField(auto_now_add=True)
    # url to an image file of the book's cover
    cover_url = models.URLField(blank=True, default="")
    cover_file = models.ImageField(upload_to="book_covers", null=True, blank=True)
    date_published = models.DateField(blank=True, null=True, default=None)
    featured = models.BooleanField(
        blank=True,
        default=False,
        help_text="whether the book should be featured on the home page - make sure "
        "it has a cover",
    )

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"{self.title} ({self.edition_id})"

    def get_absolute_url(self):
        return reverse("view_book", args=(self.edition_id,))

    @property
    @admin.display(description="Authors' Names")
    def authors_name_string(self) -> str:
        all_authors = [author.name for author in self.authors.all()]
        if len(all_authors) == 1:
            return all_authors[0]
        elif len(all_authors) == 2:
            return all_authors[0] + " and " + all_authors[1]
        else:
            # concatenate the last two items of the list with 'and' in the middle
            all_authors[-2] = all_authors[-2] + ", and " + all_authors[-1]
            # combine all the author names into a single string separated by commas,
            # ignoring the last item as it has already been included in the line above
            return ", ".join(all_authors[:-1])

    @property
    def available_copies(self) -> QuerySet[BookCopy]:
        return self.copies.filter(current_loan__isnull=True, reservation__isnull=True)

    @property
    def num_copies_available(self) -> int:
        return self.available_copies.count()

    @property
    def other_editions(self) -> QuerySet[Book]:
        return Book.objects.filter(work_id=self.work_id).exclude(
            edition_id=self.edition_id
        )

    @property
    def copy_next_available(self) -> Optional[date]:
        """Returns the soonest due date of the copies that are currently unavailable,
        or null if they're all available."""
        if self.num_copies_available < self.copies.count():
            return min(copy.due_date for copy in self.copies.all() if copy.due_date)

    @classmethod
    def from_isbn(cls, isbn: str) -> Book:
        """
        Get or create a Book object from an isbn, pulling any required data on the
        book or its authors from the OpenLibrary API. Could raise APINotFoundError.

        Args:
            isbn: isbn-10 or isbn-13 of the book

        Returns:
            the created Book object
        """
        # cleans isbn to ensure it doesn't have any extra dashes, spaces, etc. that
        # would stop the database lookup from successfully finding the existing book
        # copy
        isbn = clean_isbn(isbn)

        # check if the book already exists, if so, simply return that
        if (book := Book.objects.filter(isbn=isbn)).exists():
            return book.get()

        # get main book data from generic Book API and extract it into a python dict
        r = requests.get(
            f"https://openlibrary.org/api/books",
            {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
        )
        data = r.json()
        if f"ISBN:{isbn}" not in data:
            raise APINotFoundError(isbn, "Book")
        book_data = data[f"ISBN:{isbn}"]

        # extract the edition id from the provided `key` field
        edition_id = get_id_from_key(book_data["key"])

        # get edition information from works API and extract it into a python dict
        r = requests.get(f"https://openlibrary.org/books/{edition_id}.json")
        edition_api_data = r.json()
        if "error" in edition_api_data:
            raise APINotFoundError(edition_id, "Book")

        # extracts the work_id from the provided nested dict
        work_id = get_id_from_key(edition_api_data["works"][0]["key"])

        # get work information from works API and extract it into a python dict
        r = requests.get(f"https://openlibrary.org/works/{work_id}.json")
        works_api_data = r.json()
        if "error" in works_api_data:
            raise APINotFoundError(edition_id, "Book")

        # extract information from dicts, doing any basic processing necessary
        title = book_data["title"]
        matches = tuple(datefinder.find_dates(book_data["publish_date"]))
        date_published = matches[0].date() if matches else None
        description = works_api_data.get("description", "")

        # get book cover from api and save as file
        cover = book_data.get("cover", None)
        cover_url = cover["large"] if cover is not None else ""
        if cover_url:
            img_temp = NamedTemporaryFile(delete=True)
            img_temp.write(urlopen(cover_url).read())
            img_temp.flush()

        # create the book object
        book = Book.objects.create(
            isbn=isbn,
            edition_id=edition_id,
            work_id=work_id,
            title=title,
            description=description,
            cover_url=cover_url,
            date_published=date_published,
        )
        # get or create its accompanying author objects
        for author_data in book_data["authors"]:
            author_id = get_id_from_key(author_data["url"])
            name = author_data["name"]
            author, _ = Author.objects.get_or_create(
                id=author_id, defaults=dict(name=name)
            )
            book.authors.add(author)
        # save book cover file
        if cover_url:
            book.cover_file.save(book.pk, File(img_temp))

        return book


class BookCopy(models.Model):
    class Meta:
        verbose_name_plural = "book copies"

    accession_code = models.PositiveIntegerField(primary_key=True)
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="copies")

    @property
    def unavailable(self):
        return hasattr(self, "current_loan") or hasattr(self, "reservation")

    @property
    def due_date(self) -> Optional[date]:
        if hasattr(self, "current_loan"):
            return self.current_loan.due_date
        elif hasattr(self, "reservation"):
            return self.reservation.expiry_date

    def __str__(self):
        return f"{self.accession_code} ({self.book.title} [{self.book.edition_id}])"

    @classmethod
    def from_isbn(cls, isbn: str, accession_code: int) -> BookCopy:
        """
        Creates a BookCopy with the provided accession code from an isbn, pulling any
        required data on the book or its authors from the OpenLibrary API. Could raise
        APINotFoundError or ObjectExistsError.

        Args:
            isbn: isbn-10 or isbn-13 of the book
            accession_code: the accession code for the BookCopy object to be created with

        Returns:
            the created BookCopy object
        """
        # check if a book copy with the provided accession code already exists
        if BookCopy.objects.filter(accession_code=accession_code).exists():
            raise ObjectExistsError(accession_code, "BookCopy")

        # creates the book copy
        book = Book.from_isbn(isbn)
        book_copy = BookCopy.objects.create(accession_code=accession_code, book=book)

        return book_copy


class Loan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        LibraryUser, on_delete=models.PROTECT, related_name="loans"
    )
    book = models.OneToOneField(
        BookCopy, on_delete=models.PROTECT, related_name="current_loan"
    )
    loan_date = models.DateField(auto_now_add=True, help_text="date the loan began")
    renewal_date = models.DateField(
        blank=True,
        default=date.today,
        help_text="date the loan was last renewed (or first began if it has never "
        "been renewed)",
    )
    renewals = models.PositiveSmallIntegerField(
        blank=True, default=0, help_text="number of renewals so far"
    )

    @property
    def due_date(self) -> date:
        return self.renewal_date + timedelta(days=self.user.loan_length)

    @property
    def overdue(self):
        return self.due_date < date.today()

    def __str__(self):
        return (
            f"{self.book.book.title} ({self.book.accession_code}) -> {self.user.username} "
            f"(until {self.due_date})"
        )

    def save(self, *args, ignore_unavailable=None, **kwargs):
        """
        Loan a book out to a user, ensuring that they are within their loan
        allowance. Could raise MaxLoansError or BookUnavailableError (if
        ignore_unavailable not passed).
        """
        # checks that the user won't be going over their loan limit when first creating
        if self._state.adding and self.user.loans.count() >= self.user.loans_allowed:
            raise MaxLoansError(self.user)

        # ensures that the book is available when first creating
        if (
            self._state.adding
            and hasattr(self.book, "reservation")
            and not ignore_unavailable
        ):
            raise BookUnavailableError(self.book)

        # creates the loan
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Return a book that a user has loaned out, adding a record of the loan to
        the history and assigning the book to any outstanding reservations.
        """
        # adds loan to history
        HistoryLoan.objects.create(
            user=self.user, book=self.book, loan_date=self.loan_date
        )

        # assign book copy to reservation (if exists)
        reservation = Reservation.objects.filter(
            copy__isnull=True, book=self.book.book
        ).first()
        if reservation:
            reservation.assign_book_copy(copy=self.book, email_on_success=True)
            reservation.save()

        # deletes the loan
        return super().delete(*args, **kwargs)

    def renew(self, force=False):
        """
        Renews the loan, performing all necessary checks and background updates.
        Could raise MaxRenewalsError (unless force=True is passed).
        """
        # checks that the user has not reached their renewal limit
        if not force and self.renewals >= self.user.renewal_limit:
            raise MaxRenewalsError(self)

        self.renewals += 1
        self.renewal_date = date.today()


class Reservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        LibraryUser, on_delete=models.PROTECT, related_name="reservations"
    )
    book = models.ForeignKey(
        Book, on_delete=models.PROTECT, related_name="reservations"
    )
    copy = models.OneToOneField(
        BookCopy,
        on_delete=models.PROTECT,
        related_name="reservation",
        blank=True,
        null=True,
    )
    # ready_since should be set when a copy is added
    ready_since = models.DateField(
        blank=True,
        null=True,
        help_text="date the reservation was ready for collection ",
    )
    off_shelves = models.BooleanField(
        blank=True,
        default=False,
        help_text="whether the book has been taken off "
        "the shelves and put in the reserved "
        "section",
    )

    def __str__(self):
        return f"{self.book.title} ({self.book.edition_id}) -> {self.user.username}"

    @property
    def needs_copy(self) -> bool:
        return self.copy is None

    @property
    def expiry_date(self) -> Optional[date]:
        if self.ready_since:
            return self.ready_since + timedelta(days=7)

    @property
    def days_to_collect(self) -> Optional[int]:
        if self.ready_since:
            days_left = 7 - (date.today() - self.ready_since).days
            return days_left

    @property
    def expired(self) -> Optional[bool]:
        if self.expiry_date:
            return self.expiry_date < date.today()

    def assign_book_copy(self, email_on_success=False, copy=None) -> Optional[bool]:
        """
        If one is available, assigns a book copy to the reservation (if it doesn't
        already have one), sending an email to the user letting them know their
        reservation is ready if requested. Doesn't call self.save(). Returns bool
        based on whether a book copy was assigned.
        """
        if not self.needs_copy:
            return None

        if copy:
            self.copy = copy
        else:
            if self.book.num_copies_available == 0:
                return False
            self.copy = self.book.available_copies.first()
        self.ready_since = datetime.now()

        if email_on_success:
            self.user.email_user(
                subject="Reservation ready for collection",
                message=f"The book you reserved, {self.book.title} by "
                f"{self.book.authors_name_string} is available to be collected from "
                f"the library. It will be held for you for seven days, before being "
                f"returned to the shelves. More information can be viewed on your "
                        f"account page on the library website.",
                fail_silently=False,
            )

        return True


class HistoryLoan(models.Model):
    user = models.ForeignKey(
        LibraryUser, on_delete=models.PROTECT, related_name="loan_history"
    )
    book = models.ForeignKey(
        BookCopy, on_delete=models.PROTECT, related_name="loan_history"
    )
    loan_date = models.DateField(help_text="date the loan began")
    returned_date = models.DateField(
        auto_now_add=True, help_text="date the book was returned"
    )

    def __str__(self):
        return (
            f"{self.book.book.title} ({self.book.accession_code}) -> {self.user.username} "
            f"({self.loan_date} to {self.returned_date})"
        )

    @property
    def duration(self):
        return self.returned_date - self.loan_date


def get_id_from_key(key_path: str, index: int = 2):
    return urlparse(key_path).path.split("/")[index]


def clean_isbn(isbn):
    return re.sub(r"\D+", r"", isbn)
