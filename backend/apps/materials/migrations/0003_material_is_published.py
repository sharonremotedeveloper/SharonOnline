"""Wave 2 (decision 3, Draft -> Published): `is_approved` becomes `is_published` and new materials start as drafts.
Existing rows keep their value, so everything public today stays public."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_audio_snippet_file_and_more'),
    ]

    operations = [
        migrations.RenameField(model_name='material', old_name='is_approved', new_name='is_published'),
        migrations.AlterField(model_name='material', name='is_published',
                              field=models.BooleanField(db_index=True, default=False)),
    ]
