from django.contrib import admin
from .models import Material

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'cefr_level', 'category', 'is_approved', 'created_at')
    list_filter = ('cefr_level', 'category', 'is_approved')
    search_fields = ('title', 'description', 'content_html')
    prepopulated_fields = {'slug': ('title',)}
