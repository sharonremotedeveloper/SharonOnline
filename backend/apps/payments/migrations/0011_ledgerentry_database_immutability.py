from django.db import migrations


TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION payments_reject_ledger_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'payments_ledgerentry is append-only';
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGERS = """
CREATE TRIGGER payments_ledgerentry_reject_update
BEFORE UPDATE ON payments_ledgerentry
FOR EACH ROW EXECUTE FUNCTION payments_reject_ledger_mutation();
CREATE TRIGGER payments_ledgerentry_reject_delete
BEFORE DELETE ON payments_ledgerentry
FOR EACH ROW EXECUTE FUNCTION payments_reject_ledger_mutation();
"""

DROP_SQL = """
DROP TRIGGER IF EXISTS payments_ledgerentry_reject_update ON payments_ledgerentry;
DROP TRIGGER IF EXISTS payments_ledgerentry_reject_delete ON payments_ledgerentry;
DROP FUNCTION IF EXISTS payments_reject_ledger_mutation();
"""


def install_postgres_immutability(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(TRIGGER_FUNCTION)
        schema_editor.execute(CREATE_TRIGGERS)


def remove_postgres_immutability(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(DROP_SQL)


class Migration(migrations.Migration):
    dependencies = [('payments', '0010_ledgerentry_fx_source_and_more')]

    operations = [
        migrations.RunPython(install_postgres_immutability, remove_postgres_immutability),
    ]
