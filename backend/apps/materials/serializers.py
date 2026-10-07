from rest_framework import serializers
from .models import Material

class MaterialListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    cefr_display = serializers.CharField(source='get_cefr_level_display', read_only=True)
    pdf_file_url = serializers.CharField(source='resolved_pdf_url', read_only=True)
    audio_snippet_url = serializers.CharField(source='resolved_audio_url', read_only=True)
    summary = serializers.CharField(source='description', read_only=True)
    estimated_minutes = serializers.SerializerMethodField()
    vocabulary = serializers.SerializerMethodField()
    discussion_questions = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = (
            'id', 'title', 'slug', 'category', 'category_display',
            'cefr_level', 'cefr_display', 'description', 'pdf_file_url',
            'audio_snippet_url', 'summary', 'estimated_minutes', 'vocabulary',
            'discussion_questions'
        )

    def get_estimated_minutes(self, obj) -> int:
        return 25

    def get_vocabulary(self, obj) -> list:
        # Material content is currently stored as HTML, not as a structured vocabulary table.
        # Return an explicit empty collection until that schema exists; never invent vocabulary from markup.
        return []

    def get_discussion_questions(self, obj) -> list:
        # See get_vocabulary: callers need a stable contract without treating unparsed HTML as structured data.
        return []

class MaterialDetailSerializer(MaterialListSerializer):
    class Meta(MaterialListSerializer.Meta):
        fields = MaterialListSerializer.Meta.fields + ('content_html', 'created_at', 'updated_at')



class MaterialAssetCommitSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=5, help_text="'pdf' or 'audio'")
    key = serializers.CharField(max_length=512)
    etag = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')

    def validate_kind(self, value):
        if value not in ('pdf', 'audio'):
            raise serializers.ValidationError("Must be 'pdf' or 'audio'.")
        return value


class MaterialAssetCommitResponseSerializer(serializers.Serializer):
    kind = serializers.CharField()
    key = serializers.CharField()
    url = serializers.CharField()
    etag = serializers.CharField()
    content_type = serializers.CharField()
