from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainSlidingSerializer

from lms.models import LibraryUser, Author, Book, BookCopy, Loan


class LibraryUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibraryUser
        fields = [
            "id",
            "username",
            "email",
            "groups",
            "loans_allowed",
            "loan_length",
            "renewal_limit",
        ]


class BasicLibraryUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibraryUser
        fields = ["id", "username"]


class BasicAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name"]


class BasicBookSerializer(serializers.ModelSerializer):
    authors = BasicAuthorSerializer(read_only=True, many=True)

    class Meta:
        model = Book
        fields = [
            "isbn",
            "edition_id",
            "title",
            "authors",
            "cover_url",
            "date_published",
        ]


class BookCopySerializer(serializers.ModelSerializer):
    book = BasicBookSerializer(read_only=True)

    class Meta:
        model = BookCopy
        fields = ["accession_code", "book", "current_loan"]


class LoanBookCopySerializer(BookCopySerializer):
    pass


class LoanSerializer(serializers.ModelSerializer):
    user = BasicLibraryUserSerializer(read_only=True)
    book = LoanBookCopySerializer()

    due_date = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    @staticmethod
    def get_due_date(instance):
        return instance.due_date

    @staticmethod
    def get_overdue(instance):
        return instance.overdue

    class Meta:
        model = Loan
        fields = [
            "id",
            "user",
            "book",
            "loan_date",
            "renewal_date",
            "renewals",
            "due_date",
            "overdue",
        ]


class BasicLoanSerializer(LoanSerializer):
    book = None


class BookBookCopySerializer(BookCopySerializer):
    book = None
    current_loan = BasicLoanSerializer(read_only=True)


class BookSerializer(serializers.ModelSerializer):
    copies = BookBookCopySerializer(read_only=True, many=True)
    authors = BasicAuthorSerializer(read_only=True, many=True)

    class Meta:
        model = Book
        fields = [
            "isbn",
            "edition_id",
            "work_id",
            "title",
            "authors",
            "cover_url",
            "date_published",
            "copies",
        ]


class AuthorSerializer(serializers.ModelSerializer):
    books = BookSerializer(many=True, read_only=True)

    class Meta:
        model = Author
        fields = ["id", "name", "books"]  # TODO: add basic book serializer


class LibraryTokenObtainSlidingSerializer(TokenObtainSlidingSerializer):  # noqa
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["name"] = user.get_full_name()
        loans = []
        for loan in user.loans.all():
            loan = BasicLoanSerializer(loan).data
            loan["due_date"] = str(loan["due_date"])
            loans.append(loan)
        token["loans"] = loans

        return token
