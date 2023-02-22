# Generated by Django 4.1.1 on 2022-12-10 21:52

import datetime
from django.conf import settings
import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import isbn_field.fields
import isbn_field.validators
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="LibraryUser",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={
                            "unique": "A user with that username already exists."
                        },
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[
                            django.contrib.auth.validators.UnicodeUsernameValidator()
                        ],
                        verbose_name="username",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="first name"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(
                        blank=True, max_length=150, verbose_name="last name"
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="email address"
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "date_joined",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="date joined"
                    ),
                ),
                (
                    "loans_allowed",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        default=3,
                        help_text="number of books the user is allowed to take out at once",
                    ),
                ),
                (
                    "loan_length",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        default=7,
                        help_text="number of days the each loan/renewal the user makes is valid for",
                    ),
                ),
                (
                    "renewal_limit",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        default=3,
                        help_text="number of times the user can renew a book",
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="Author",
            fields=[
                (
                    "id",
                    models.CharField(
                        max_length=20,
                        primary_key=True,
                        serialize=False,
                        validators=[
                            django.core.validators.RegexValidator(
                                "OL.*",
                                message="Open library IDs should start with `OL`",
                            )
                        ],
                    ),
                ),
                ("name", models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name="Book",
            fields=[
                (
                    "isbn",
                    isbn_field.fields.ISBNField(
                        max_length=28,
                        primary_key=True,
                        serialize=False,
                        validators=[isbn_field.validators.ISBNValidator],
                        verbose_name="ISBN",
                    ),
                ),
                (
                    "edition_id",
                    models.CharField(
                        max_length=20,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "OL.*",
                                message="Open library IDs should start with `OL`",
                            )
                        ],
                    ),
                ),
                (
                    "work_id",
                    models.CharField(
                        max_length=20,
                        validators=[
                            django.core.validators.RegexValidator(
                                "OL.*",
                                message="Open library IDs should start with `OL`",
                            )
                        ],
                    ),
                ),
                ("title", models.CharField(max_length=150)),
                ("cover_url", models.URLField(blank=True, default="")),
                (
                    "cover_file",
                    models.ImageField(blank=True, null=True, upload_to="book_covers"),
                ),
                (
                    "date_published",
                    models.DateField(blank=True, default=None, null=True),
                ),
                (
                    "authors",
                    models.ManyToManyField(related_name="books", to="lms.author"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BookCopy",
            fields=[
                (
                    "accession_code",
                    models.PositiveIntegerField(primary_key=True, serialize=False),
                ),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="copies",
                        to="lms.book",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "book copies",
            },
        ),
        migrations.CreateModel(
            name="Loan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "loan_date",
                    models.DateField(
                        auto_now_add=True, help_text="date the loan began"
                    ),
                ),
                (
                    "renewal_date",
                    models.DateField(
                        blank=True,
                        default=datetime.date.today,
                        help_text="date the loan was last renewed (or first began if it has never been renewed ",
                    ),
                ),
                (
                    "renewals",
                    models.PositiveSmallIntegerField(
                        blank=True, default=0, help_text="number of renewals so far"
                    ),
                ),
                (
                    "book",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="current_loan",
                        to="lms.bookcopy",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="loans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="HistoryLoan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("loan_date", models.DateField(help_text="date the loan began")),
                (
                    "returned_date",
                    models.DateField(
                        auto_now_add=True, help_text="date the book was returned"
                    ),
                ),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="loan_history",
                        to="lms.bookcopy",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="loan_history",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]