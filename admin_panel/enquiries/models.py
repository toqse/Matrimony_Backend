from django.db import models

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch


class Enquiry(models.Model):
    SOURCE_CHOICES = [
        ("website", "Website"),
        ("walk-in", "Walk-in"),
        ("phone", "Phone"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("interested", "Interested"),
        ("converted", "Converted"),
        ("lost", "Lost"),
    ]

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    assigned_to = models.ForeignKey(
        AdminUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_enquiries",
    )
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        AdminUser,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_enquiries",
    )

    class Meta:
        ordering = ["-created_at"]


class EnquiryNote(models.Model):
    enquiry = models.ForeignKey(
        Enquiry, on_delete=models.CASCADE, related_name="enquiry_notes"
    )
    text = models.TextField()
    created_by = models.ForeignKey(
        AdminUser,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
