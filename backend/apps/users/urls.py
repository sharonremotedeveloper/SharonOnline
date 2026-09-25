from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, CurrentUserView, CustomTokenObtainPairView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='auth-token-obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('me/', CurrentUserView.as_view(), name='auth-current-user'),
]
