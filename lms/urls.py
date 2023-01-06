from django.conf.urls.static import static
from django.urls import path, include
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenRefreshSlidingView,
)

from lms_base import settings
from . import views

router = routers.DefaultRouter()
router.register(r"library-users", views.LibraryUserViewSet)
router.register(r"authors", views.AuthorViewSet)
router.register(r"books", views.BookViewSet)
router.register(r"loans", views.LoanViewSet)
# TODO: user accounts page should be at '/accounts/profile'
urlpatterns = [
    path("TESTING/", views.TESTING.as_view()),
    path("", views.MainHome.as_view(), name="main_home"),
    path("kiosk/", views.KioskHome.as_view(), name="kiosk_home"),
    path("kiosk/take-out/", views.KioskTakeOut.as_view(), name="kiosk_take_out"),
    path("kiosk/return/<uuid:pk>/", views.KioskReturn.as_view(), name="kiosk_return"),
    path(
        "api/token/", views.LibraryTokenObtainSlidingView.as_view(), name="token_obtain"
    ),
    path("api/token/refresh/", TokenRefreshSlidingView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("admin/import-book/", views.import_book, name="import_book"),
    path("book/<edition_id>/", views.BookDetailView.as_view(), name="view_book"),
    path("author/<author_id>/", views.AuthorDetailView.as_view(), name="view_author"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/register/", views.UserRegistrationView.as_view(), name="register"),
    path("accounts/profile/", views.UserProfileView.as_view(), name="user_profile"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
