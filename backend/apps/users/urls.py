from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, CurrentUserView, CustomTokenObtainPairView, LogoutView, PasswordResetRequestView, PasswordResetConfirmView,
    PasswordChangeView, EmailVerifyRequestView, EmailVerifyConfirmView,
    SupportInquiryView,
    UserDataExportView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='auth-token-obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', CurrentUserView.as_view(), name='auth-current-user'),
    path('me/data-export/', UserDataExportView.as_view(), name='auth-user-data-export'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('password-change/', PasswordChangeView.as_view(), name='auth-password-change'),
    path('verify-email/', EmailVerifyRequestView.as_view(), name='auth-verify-email-request'),
    path('verify-email/confirm/', EmailVerifyConfirmView.as_view(), name='auth-verify-email-confirm'),
    path('inquiries/', SupportInquiryView.as_view(), name='auth-support-inquiry'),
]
