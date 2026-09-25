from rest_framework import serializers
from .models import Material

class MaterialListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    cefr_display = serializers.CharField(source='get_cefr_level_display', read_only=True)

    class Meta:
        model = Material
        fields = ('id', 'title', 'slug', 'category', 'category_display', 'cefr_level', 'cefr_display', 'description', 'pdf_file_url')

class MaterialDetailSerializer(MaterialListSerializer):
    class Meta(MaterialListSerializer.Meta):
        fields = MaterialListSerializer.Meta.fields + ('content_html', 'created_at', 'updated_at')
