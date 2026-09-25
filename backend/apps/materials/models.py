from django.db import models
import uuid

class Material(models.Model):
    class CEFRLevel(models.TextChoices):
        A1 = 'A1', 'Beginner A1'
        A2 = 'A2', 'Elementary A2'
        B1 = 'B1', 'Intermediate B1'
        B2 = 'B2', 'Upper-Intermediate B2'
        C1 = 'C1', 'Advanced C1'
        C2 = 'C2', 'Proficient C2'

    class Category(models.TextChoices):
        DAILY_NEWS = 'daily_news', 'Daily News & Discussion'
        FREETALK = 'freetalk', 'FreeTalk Conversation Prompts'
        BUSINESS = 'business', 'Business English & Professional'
        TEST_PREP = 'test_prep', 'Job Interview & Test Prep'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    cefr_level = models.CharField(max_length=4, choices=CEFRLevel.choices, db_index=True)
    description = models.TextField(blank=True)
    content_html = models.TextField(blank=True, help_text="Structured HTML content: article text, vocab definitions, discussion questions")
    pdf_file_url = models.URLField(blank=True, help_text="Cloudflare R2 link for student/teacher worksheet download")
    is_approved = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cefr_level', 'title']

    def __str__(self):
        return f"[{self.cefr_level}] {self.title} ({self.get_category_display()})"
