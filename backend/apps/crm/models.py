import uuid
from django.db import models
from django.conf import settings

class StudentTutorDossier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.CASCADE, related_name='student_dossiers')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tutor_dossiers')
    private_pedagogical_notes = models.TextField(blank=True, help_text="Confidential notes on student progress, learning style, and focus areas")
    common_grammar_mistakes = models.JSONField(default=list, help_text="List of recurring grammar slips: ['articles', 'conditionals']")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['teacher', 'student'], name='unique_teacher_student_dossier')
        ]

    def __str__(self):
        return f"Dossier: {self.teacher.user.username} -> {self.student.username}"
