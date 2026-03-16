"""
Management command to update apidoc.txt from the codebase.
Usage: python manage.py update_apidoc
Writes/overwrites Backend/apidoc.txt with current API documentation.
Extend this command to introspect URLs and view docstrings for full auto-generation.
"""
from django.core.management.base import BaseCommand
from pathlib import Path


class Command(BaseCommand):
    help = 'Update apidoc.txt (currently ensures file exists; extend to auto-generate from URLs/views).'

    def handle(self, *args, **options):
        apidoc_path = Path(__file__).resolve().parent.parent.parent.parent / 'apidoc.txt'
        if not apidoc_path.exists():
            apidoc_path.write_text(
                '# API documentation - run the server and see apidoc.txt in Backend folder for full doc.\n',
                encoding='utf-8',
            )
            self.stdout.write(self.style.SUCCESS(f'Created {apidoc_path}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'apidoc.txt exists at {apidoc_path}. Edit it or extend this command to auto-generate from URLs.'))
        return
