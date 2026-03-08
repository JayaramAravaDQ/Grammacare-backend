from django.urls import path
from . import views

urlpatterns = [
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/user/", views.user_view),
    path("chat/", views.chat_view),
    path("chat", views.chat_view),  # no slash (e.g. old frontend or proxy); same view
    path("history/", views.history_view),
    path("history", views.history_view),
]
