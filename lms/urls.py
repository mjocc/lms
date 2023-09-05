from django.conf.urls.static import static
from django.urls import path, include, re_path

from lms_base import settings
from . import views

# define urlconf to map paths to views for lms app
urlpatterns = [
    # main site
    path("", views.MainHome.as_view(), name="main_home"),
    re_path(
        r"^search/(?P<type>books|authors)/$", views.SearchView.as_view(), name="search"
    ),
    path("book/<edition_id>/", views.BookDetailView.as_view(), name="view_book"),
    path("author/<author_id>/", views.AuthorDetailView.as_view(), name="view_author"),
    path("reserve/<edition_id>/", views.ReserveView.as_view(), name="reserve_book"),
    path("renew/<uuid:pk>/", views.RenewalView.as_view(), name="renew_loan"),

    # account management
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/register/", views.UserRegistrationView.as_view(), name="register"),
    path("accounts/profile/", views.UserProfileView.as_view(), name="user_profile"),

    # kiosk site
    path("kiosk/", views.KioskHome.as_view(), name="kiosk_home"),
    path("kiosk/take-out/", views.KioskTakeOut.as_view(), name="kiosk_take_out"),
    path("kiosk/return/<uuid:pk>/", views.KioskReturn.as_view(), name="kiosk_return"),

    # admin site (django defaults included in lms_base urls.py)
    path("admin/import-book/", views.import_book, name="import_book"),
    path(
        "admin/generate-accession-codes/",
        views.AccessionCodeGenerationView.as_view(),
        name="generate_accession_codes",
    ),
    path("admin/activate-kiosk/", views.activate_kiosk, name="activate_kiosk"),
    path("admin/deactivate-kiosk/", views.deactivate_kiosk, name="deactivate_kiosk"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# pass static file configuration
