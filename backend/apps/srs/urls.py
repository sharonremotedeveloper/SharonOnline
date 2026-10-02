from django.urls import path
from apps.bookings.views import SubmitReviewView
from apps.srs.views import (
    StudentLessonsListView,
    StudentFlashcardsListView,
    UpdateFlashcardMasteryView,
    StudentProfileView,
)

urlpatterns = [
    path('lessons/', StudentLessonsListView.as_view(), name='student-lessons-list'),
    path('flashcards/', StudentFlashcardsListView.as_view(), name='student-flashcards-list'),
    path('flashcards/<uuid:pk>/mastery/', UpdateFlashcardMasteryView.as_view(), name='student-flashcard-mastery'),
    path('bookings/<uuid:pk>/review/', SubmitReviewView.as_view(), name='student-lesson-review'),
    path('profile/', StudentProfileView.as_view(), name='student-profile'),
]
