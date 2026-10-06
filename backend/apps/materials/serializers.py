from rest_framework import serializers
from .models import Material

class MaterialListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    cefr_display = serializers.CharField(source='get_cefr_level_display', read_only=True)
    pdf_file_url = serializers.CharField(source='resolved_pdf_url', read_only=True)
    audio_snippet_url = serializers.CharField(source='resolved_audio_url', read_only=True)

    class Meta:
        model = Material
        fields = (
            'id', 'title', 'slug', 'category', 'category_display',
            'cefr_level', 'cefr_display', 'description', 'pdf_file_url',
            'audio_snippet_url'
        )

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
