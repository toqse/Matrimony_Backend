from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from admin_panel.branches.models import Branch
from admin_panel.subscriptions.models import CustomerStaffAssignment
from plans.models import Transaction

from .models import Commission


@receiver(post_save, sender=Transaction)
def create_commission_on_subscription_purchase(sender, instance: Transaction, created, **kwargs):
    if not created:
        return
    if instance.transaction_type != Transaction.TYPE_PLAN_PURCHASE:
        return
    if instance.payment_status != Transaction.STATUS_SUCCESS:
        return
    if not instance.user_id:
        return
    subscription = getattr(instance.user, "user_plan", None)
    if not subscription:
        return
    assignment = CustomerStaffAssignment.objects.filter(user=instance.user).select_related("staff", "staff__branch").first()
    if not assignment or not assignment.staff_id or assignment.staff.is_deleted:
        return

    branch = assignment.staff.branch
    if not branch:
        user_branch = getattr(instance.user, "branch", None)
        if user_branch:
            branch = Branch.objects.filter(code=user_branch.code).first()
    if not branch:
        return

    sale_amount = Decimal(instance.total_amount or 0)
    commission_rate = Decimal(assignment.staff.commission_rate or 0)
    commission_amt = (sale_amount * commission_rate) / Decimal("100")

    Commission.objects.create(
        staff=assignment.staff,
        subscription=subscription,
        customer=instance.user,
        branch=branch,
        sale_amount=sale_amount,
        commission_rate=commission_rate,
        commission_amt=commission_amt,
        status=Commission.STATUS_PENDING,
    )
