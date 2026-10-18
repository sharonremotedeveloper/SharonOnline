from django.contrib import admin
from .models import Material

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'cefr_level', 'category', 'is_published', 'has_pdf', 'has_audio', 'created_at')
    list_filter = ('cefr_level', 'category', 'is_published')
    search_fields = ('title', 'description', 'content_html')
    prepopulated_fields = {'slug': ('title',)}
    # Files are uploaded on the web admin page (/admin/materials), which checks type, size and content; a file chosen here
    # would go straight to public storage unchecked (docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md risk 2).
    readonly_fields = ('pdf_file', 'audio_snippet_file')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'category', 'cefr_level', 'description', 'is_published')
        }),
        ('Lesson Content (HTML)', {
            'fields': ('content_html',)
        }),
        ('Cloudflare R2 Assets ($0 Egress)', {
            'fields': ('pdf_file', 'pdf_file_url', 'audio_snippet_file', 'audio_snippet_url'),
            'description': 'Worksheet PDFs and listening audio files stored on Cloudflare R2. Upload files on the web admin '
                           'page /admin/materials (it checks them).'
        }),
    )

    def has_pdf(self, obj):
        return bool(obj.pdf_file or obj.pdf_file_url)
    has_pdf.boolean = True
    has_pdf.short_description = "PDF"

    def has_audio(self, obj):
        return bool(obj.audio_snippet_file or obj.audio_snippet_url)
    has_audio.boolean = True
    has_audio.short_description = "Audio"

