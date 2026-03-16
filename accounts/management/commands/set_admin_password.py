"""
Set password for a staff/superuser so you can log in to /admin/.
Run this in the SAME environment as your running server (e.g. inside Docker if you use Docker).
Usage:
  python manage.py set_admin_password admin4@gmail.com 'YourNewPassword'
  docker-compose exec django python manage.py set_admin_password admin4@gmail.com 'YourNewPassword'
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Set password for an admin user (by email) so you can log in to Django admin."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="Admin user email (USERNAME_FIELD)")
        parser.add_argument("password", type=str, help="New password to set")

    def handle(self, *args, **options):
        email = (options["email"] or "").strip()
        password = options["password"]
        if not email:
            self.stderr.write(self.style.ERROR("Email is required."))
            return
        if not password:
            self.stderr.write(self.style.ERROR("Password is required."))
            return
        user = User.objects.filter(email=email).first()
        if not user:
            self.stderr.write(self.style.ERROR(f"No user with email '{email}' found."))
            return
        user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.save(update_fields=["password", "is_active", "is_staff"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Password set for {email}. You can log in at /admin/ with this email and the new password."
            )
        )
