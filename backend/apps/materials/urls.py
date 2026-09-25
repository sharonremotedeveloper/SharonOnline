from django.urls import path
from .views import MaterialListView, MaterialDetailView

urlpatterns = [
    path('', MaterialListView.as_view(), name='material-list'),
    path('<slug:slug>/', MaterialDetailView.as_view(), name='material-detail'),
]
