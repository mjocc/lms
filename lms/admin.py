from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.files import File
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import ngettext
from django_object_actions import DjangoObjectActions, action

from .models import LibraryUser, Author, Book, BookCopy, Loan, HistoryLoan


class BookAdmin(DjangoObjectActions, admin.ModelAdmin):
    actions = ["download_image"]

    @admin.action(description="Download images from cover_url")
    def download_image(self, request, queryset):
        images_downloaded = 0
        for obj in queryset:
            if obj.cover_url and not obj.cover_file:
                img_temp = NamedTemporaryFile(delete=True)
                img_temp.write(urlopen(obj.cover_url).read())
                img_temp.flush()
                obj.cover_file.save(obj.pk, File(img_temp))
                images_downloaded += 1
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

    @action(label="Import book", description="Import book from ISBN")
    def import_book(self, request, queryset):
        return HttpResponseRedirect(reverse("import_book"))

    changelist_actions = ("import_book",)


admin.site.register(LibraryUser, UserAdmin)
admin.site.register(Book, BookAdmin)

admin.site.register(Author)
admin.site.register(BookCopy)
admin.site.register(Loan)
admin.site.register(HistoryLoan)

admin.site.site_header = "Librarian/Volunteer System"
admin.site.site_title = "LMS"
admin.site.index_title = "Management"
