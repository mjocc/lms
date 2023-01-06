from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import urlopen

import datefinder
import requests
from django.contrib.auth.models import AbstractUser
from django.core.files import File
from django.core.validators import RegexValidator
from django.db import models
from isbn_field import ISBNField

from lms.errors import (
    ObjectExistsError,
    APINotFoundError,
    MaxLoansError,
    MaxRenewalsError,
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
        help_text="number of days the each loan/renewal the user makes is valid for",
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
    cover_url = models.URLField(blank=True, default="")
    cover_file = models.ImageField(upload_to="book_covers", null=True, blank=True)
    date_published = models.DateField(blank=True, null=True, default=None)

    def __str__(self):
        return f"{self.title} ({self.edition_id})"

    @property
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
    def num_copies_available(self) -> int:
        return self.copies.filter(current_loan__isnull=True).count()

    @classmethod
    def from_isbn(cls, isbn: str) -> Book:
        # TODO: redo using google books api?
        #   https://www.googleapis.com/books/v1/volumes?q=isbn:9780525559474
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

        # get work information from works API and extract it into a python dict
        r = requests.get(f"https://openlibrary.org/books/{edition_id}.json")
        edition_api_data = r.json()
        if "error" in edition_api_data:
            raise APINotFoundError(edition_id, "Book")

        # extracts the work_id from the provided nested dict
        work_id = get_id_from_key(edition_api_data["works"][0]["key"])
        # fixme: this only considers the first work in the list, should it do more?

        # extract information from dict, doing any basic processing necessary
        title = book_data["title"]
        matches = tuple(datefinder.find_dates(book_data["publish_date"]))
        date_published = matches[0].date() if matches else None

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
    def on_loan(self):
        return hasattr(self, "current_loan")

    def __str__(self):
        return f"{str(self.book)} — {self.accession_code}"

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
        "been renewed ",
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

    def save(self, *args, **kwargs):
        """
        Loan a book out to a user, ensuring that they are within their loan
        allowance. Could raise MaxLoansError.
        """
        # checks that the user won't be going over their loan limit
        if self.user.loans.count() >= self.user.loans_allowed:
            raise MaxLoansError(self.user)

        # creates the loan
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Return a book that a user has loaned out, adding a record of the loan to
        the history.
        """
        # adds loan to history
        HistoryLoan.objects.create(
            user=self.user, book=self.book, loan_date=self.loan_date
        )

        # deletes the loan
        super().delete(*args, **kwargs)

    def renew(self):
        """
        Renews the loan, performing all necessary checks and background updates.
        Could raise MaxRenewalsError.
        """
        # checks that the user has not reached their renewal limit
        if self.renewals >= self.user.renewal_limit:
            raise MaxRenewalsError(self)

        self.renewals += 1
        self.renewal_date = date.today()


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


def get_id_from_key(key_path: str, index: int = 2):
    return urlparse(key_path).path.split("/")[index]


def clean_isbn(isbn):
    return re.sub(r"\D+", r"", isbn)
