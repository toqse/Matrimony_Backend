from pprint import pformat

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Print the effective Django DATABASES setting.'

    def handle(self, *args, **options):
        self.stdout.write(pformat(settings.DATABASES))
