import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class StudentFlashcard(models.Model):
    class Mastery(models.TextChoices):
        NEW = 'new', 'New'
        LEARNING = 'learning', 'Learning'
        MASTERED = 'mastered', 'Mastered'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flashcards')
    word = models.CharField(max_length=128, db_index=True)
    phonetic = models.CharField(max_length=128, blank=True)
    part_of_speech = models.CharField(max_length=64, blank=True)
    definition = models.TextField()
    example_sentence = models.TextField(blank=True)
    lesson_source = models.CharField(max_length=255, blank=True, help_text="e.g. High-Stakes Contract Negotiations (Sharon M.)")
    mastery = models.CharField(max_length=20, choices=Mastery.choices, default=Mastery.NEW, db_index=True)
    review_count = models.PositiveIntegerField(default=0)
    next_review_due = models.DateField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_review_due', 'created_at']

    def __str__(self):
        return f"{self.word} ({self.mastery}) - {self.student.username}"
