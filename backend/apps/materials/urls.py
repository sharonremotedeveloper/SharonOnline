from django.urls import path
from .views import MaterialAssetCommitView, MaterialListView, MaterialDetailView

urlpatterns = [
    path('', MaterialListView.as_view(), name='material-list'),
    path('<uuid:material_id>/assets/commit/', MaterialAssetCommitView.as_view(), name='material-asset-commit'),
    path('<slug:slug>/', MaterialDetailView.as_view(), name='material-detail'),
]
