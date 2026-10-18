"""Wave 2 (decision 3, Draft -> Published): the field `is_approved` is renamed `is_published` in Python and new materials start
as drafts. The database column keeps its name (`db_column='is_approved'`) and nothing is altered in the database, so this is
expand-only: the previous API release keeps working against the same table while a new release rolls out. Existing rows keep
their value, so everything public today stays public. (The new-row default is applied by Django, not by the database.)"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_audio_snippet_file_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name='material', old_name='is_approved', new_name='is_published'),
                migrations.AlterField(model_name='material', name='is_published',
                                      field=models.BooleanField(db_column='is_approved', db_index=True, default=False)),
            ],
            database_operations=[],
        ),
    ]
