"""
Plan and interest APIs: Admin Plan CRUD, List Plans, Purchase, Send Interest, Chat Permission, My Plan.
"""
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.permissions import IsAdmin
from user_settings.models import UserSettings
from django.db import transaction
from .models import Interest, Plan, ServiceCharge, UserPlan, Transaction, Conversation
from .serializers import (
    PlanSerializer,
    PlanPurchaseSerializer,
    PayRemainingServiceSerializer,
    InterestListSerializer,
)
from .services import (
    PlanLimitService,
    can_send_interest,
    can_chat,
    can_view_contact,
    get_plan_info_for_response,
    is_plan_expired,
    plan_expired_response,
    get_user_plan_status,
    has_accepted_interest_between,
)


# --- Admin Plan CRUD ---
class AdminPlanViewSet(ModelViewSet):
    """
    GET/POST /api/v1/admin/plans/
    GET/PATCH/DELETE /api/v1/admin/plans/{id}/
    Admin only.
    """
    queryset = Plan.objects.all().order_by('name')
    serializer_class = PlanSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']


# --- User Plan APIs ---
class PlanListView(APIView):
    """
    GET /api/v1/plans/
    List active plans with service_charge and total_price based on request user's gender.
    Auth: Required (JWT) so service charge is applied by user gender.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by('price')
        # Service charge from user profile (gender): Male 15000, Female 10000, Other 5000
        gender = getattr(request.user, 'gender', None) or 'M'
        if not gender:
            gender = 'M'
        try:
            sc = ServiceCharge.objects.get(gender=gender)
            service_charge = sc.amount
        except ServiceCharge.DoesNotExist:
            service_charge = Decimal('0')
        out = []
        for plan in plans:
            total = service_charge - (plan.price or Decimal('0'))
            out.append({
                'id': plan.id,
                'name': plan.name,
                'price': float(plan.price or 0),
                'service_charge': float(service_charge),
                'total_price': float(total),
                'duration_days': plan.duration_days,
                'profile_view_limit': plan.profile_view_limit,
                'interest_limit': plan.interest_limit,
                'chat_limit': plan.chat_limit,
                'horoscope_match_limit': plan.horoscope_match_limit,
                'contact_view_limit': plan.contact_view_limit,
                'description': plan.description or '',
            })
        return Response({
            'success': True,
            'data': {
                'plans': out,
                'gender': gender,
            },
        }, status=status.HTTP_200_OK)


class PlanPurchaseView(APIView):
    """
    POST /api/v1/plans/purchase/
    Body: {
      "plan_id": 3,
      "payment_method": "razorpay",
      "payment_option": "plan_only" | "full"
    }

    payment_option:
      plan_only (default) — user pays only plan.price (registration fee).
                            Remaining service charge can be paid later via
                            POST /api/v1/plans/pay-remaining-service/.
      full                — user pays the remaining amount upfront
                            (service_charge - plan.price).

    Creates/updates UserPlan and records a Transaction.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        ser = PlanPurchaseSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Validation failed.', 'details': ser.errors},
            }, status=status.HTTP_400_BAD_REQUEST)

        plan_id = ser.validated_data['plan_id']
        payment_method = ser.validated_data['payment_method']
        payment_option = ser.validated_data['payment_option']
        plan = Plan.objects.get(pk=plan_id)
        user = request.user
        today = timezone.now().date()

        with transaction.atomic():
            # Lock the user's plan row (if any) to avoid concurrent upgrade double-counting.
            any_up = (
                UserPlan.objects
                .select_for_update()
                .select_related('plan')
                .filter(user=user)
                .first()
            )
            # Carry-forward applies only if still active and not expired.
            old_up = any_up if (any_up and any_up.is_active and (any_up.valid_until is None or any_up.valid_until >= today)) else None

            gender = getattr(user, 'gender', None) or 'M'
            try:
                sc = ServiceCharge.objects.get(gender=gender)
                service_charge_total = sc.amount
            except ServiceCharge.DoesNotExist:
                service_charge_total = Decimal('0')

            plan_price = plan.price or Decimal('0')
            # remaining = service_charge - plan_price (the amount still owed after registration fee)
            remaining_amount = max(service_charge_total - plan_price, Decimal('0'))

            if payment_option == PlanPurchaseSerializer.PAYMENT_OPTION_FULL:
                # User pays the remaining service charge upfront
                amount_paid = remaining_amount
                service_charge_paid = service_charge_total
                payment_message = 'Plan purchased with full payment.'
            else:
                # plan_only: user pays only the registration/plan fee now
                amount_paid = plan_price
                service_charge_paid = Decimal('0')
                payment_message = 'Plan purchased. Remaining service charge can be paid later.'

            txn = Transaction.objects.create(
                user=user,
                plan=plan,
                amount=amount_paid,
                service_charge=service_charge_total,
                total_amount=amount_paid,
                payment_method=payment_method,
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                transaction_id='',
            )

            valid_from = today
            if old_up:
                # Carry forward remaining quotas from old plan and extend validity.
                def _remaining(plan_limit, bonus, used):
                    if plan_limit == 0:
                        return 0  # unlimited plans can't be carried forward as a finite bonus
                    effective = (plan_limit or 0) + (bonus or 0)
                    return max(0, effective - (used or 0))

                carry_profile = _remaining(old_up.plan.profile_view_limit, getattr(old_up, 'profile_view_bonus', 0), old_up.profile_views_used)
                carry_interest = _remaining(old_up.plan.interest_limit, getattr(old_up, 'interest_bonus', 0), old_up.interests_used)
                carry_chat = _remaining(old_up.plan.chat_limit, getattr(old_up, 'chat_bonus', 0), old_up.chat_used)
                carry_contact = _remaining(old_up.plan.contact_view_limit, getattr(old_up, 'contact_view_bonus', 0), old_up.contact_views_used)
                carry_horo = _remaining(old_up.plan.horoscope_match_limit, getattr(old_up, 'horoscope_bonus', 0), old_up.horoscope_used)

                valid_until = (old_up.valid_until or today) + timezone.timedelta(days=plan.duration_days)
                payment_message = 'Plan upgraded successfully with carry forward.'
            else:
                carry_profile = carry_interest = carry_chat = carry_contact = carry_horo = 0
                valid_until = valid_from + timezone.timedelta(days=plan.duration_days)

            UserPlan.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'price_paid': plan_price,
                    'service_charge': service_charge_total,
                    'service_charge_paid': service_charge_paid,
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                    'is_active': True,
                    'profile_view_bonus': carry_profile,
                    'interest_bonus': carry_interest,
                    'chat_bonus': carry_chat,
                    'horoscope_bonus': carry_horo,
                    'contact_view_bonus': carry_contact,
                    'profile_views_used': 0,
                    'interests_used': 0,
                    'chat_used': 0,
                    'horoscope_used': 0,
                    'contact_views_used': 0,
                },
            )

        service_charge_remaining = service_charge_total - service_charge_paid

        return Response({
            'success': True,
            'message': payment_message,
            'data': {
                'transaction_id': txn.id,
                'plan_name': plan.name,
                'payment_option': payment_option,
                'amount_paid': float(amount_paid),
                'service_charge_remaining': float(service_charge_remaining),
                'valid_until': valid_until.isoformat(),
                'carry_forward': {
                    'profile_views': int(carry_profile),
                    'interests': int(carry_interest),
                    'chats': int(carry_chat),
                    'contacts': int(carry_contact),
                    'horoscope': int(carry_horo),
                },
            },
        }, status=status.HTTP_201_CREATED)


class PayRemainingServiceView(APIView):
    """
    POST /api/v1/plans/pay-remaining-service/
    Body: { "payment_method": "razorpay" }
    After admin has confirmed service is required, customer pays the remaining service charge (e.g. 14501).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        ser = PayRemainingServiceSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Validation failed.', 'details': ser.errors},
            }, status=status.HTTP_400_BAD_REQUEST)
        payment_method = ser.validated_data['payment_method']
        user = request.user
        try:
            user_plan = UserPlan.objects.get(user=user, is_active=True)
        except UserPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'No active plan found. Purchase a plan first.'},
            }, status=status.HTTP_404_NOT_FOUND)
        service_charge_total = user_plan.service_charge or Decimal('0')
        service_charge_paid = user_plan.service_charge_paid or Decimal('0')
        remaining = service_charge_total - service_charge_paid
        if remaining <= 0:
            return Response({
                'success': True,
                'message': 'No remaining service charge to pay.',
                'data': {'amount_paid': 0, 'service_charge_remaining': 0},
            }, status=status.HTTP_200_OK)
        txn = Transaction.objects.create(
            user=user,
            plan=user_plan.plan,
            amount=remaining,
            service_charge=remaining,
            total_amount=remaining,
            payment_method=payment_method,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_id='',
        )
        user_plan.service_charge_paid = service_charge_total
        user_plan.save(update_fields=['service_charge_paid', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Remaining service charge paid successfully.',
            'data': {
                'transaction_id': txn.id,
                'amount_paid': float(remaining),
                'service_charge_remaining': 0,
            },
        }, status=status.HTTP_201_CREATED)


class SendInterestView(APIView):
    """
    POST /api/v1/interests/send/
    Body: { "receiver_matri_id": "AM100023" }
    Check interest limit; decrement on success via PlanLimitService.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        receiver_matri_id = (request.data.get('receiver_matri_id') or '').strip()
        if not receiver_matri_id:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'receiver_matri_id is required.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Require an active plan before checking interest limits
        plan_status = get_user_plan_status(request.user)
        if plan_status != 'active':
            return Response(plan_expired_response(request.user), status=status.HTTP_403_FORBIDDEN)

        can_send, remaining = can_send_interest(request.user)
        if not can_send:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Interest limit reached. Upgrade your plan.'}
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            receiver = User.objects.get(matri_id=receiver_matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'}
            }, status=status.HTTP_404_NOT_FOUND)

        # Receiver may allow only premium users to send interest
        try:
            recv_settings = receiver.user_settings
            if recv_settings.interest_request_permission == UserSettings.INTEREST_PREMIUM:
                if get_user_plan_status(request.user) != 'active':
                    return Response({
                        'success': False,
                        'error': {'code': 403, 'message': 'Only premium users can send interest to this profile.'}
                    }, status=status.HTTP_403_FORBIDDEN)
        except UserSettings.DoesNotExist:
            pass

        if receiver.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Cannot send interest to yourself.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        # If connection already exists (interest accepted in either direction),
        # do not allow sending again—return a clear message for UI.
        if has_accepted_interest_between(request.user, receiver):
            return Response({
                'success': True,
                'message': 'Already connected.',
                'data': {'status': Interest.STATUS_ACCEPTED},
            }, status=status.HTTP_200_OK)

        # If the receiver already sent an interest request to the current user,
        # don't create a duplicate request—ask user to accept instead.
        incoming = Interest.objects.filter(
            sender=receiver,
            receiver=request.user,
            status=Interest.STATUS_PENDING,
        ).first()
        if incoming:
            return Response({
                'success': True,
                'message': 'This user already sent you an interest request. Please accept it.',
                'data': {'status': Interest.STATUS_PENDING, 'interest_id': incoming.id},
            }, status=status.HTTP_200_OK)

        _, created = Interest.objects.get_or_create(
            sender=request.user,
            receiver=receiver,
            defaults={'status': Interest.STATUS_PENDING}
        )
        if not created:
            return Response({
                'success': True,
                'message': 'Interest already sent.',
                'data': {'status': Interest.STATUS_PENDING},
            }, status=status.HTTP_200_OK)

        PlanLimitService.consume_interest(request.user)

        return Response({
            'success': True,
            'message': 'Interest sent successfully.'
        }, status=status.HTTP_200_OK)


class MyInterestsView(APIView):
    """
    GET /api/v1/interests/my/
    Returns interests sent and received by the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sent_qs = Interest.objects.filter(sender=user).select_related('receiver').order_by('-created_at')
        received_qs = Interest.objects.filter(receiver=user).select_related('sender').order_by('-created_at')

        sent_ser = InterestListSerializer(
            sent_qs, many=True, context={'direction': 'sent', 'request': request}
        )
        received_ser = InterestListSerializer(
            received_qs, many=True, context={'direction': 'received', 'request': request}
        )

        return Response({
            'success': True,
            'data': {
                'sent': {
                    'total': sent_qs.count(),
                    'results': sent_ser.data,
                },
                'received': {
                    'total': received_qs.count(),
                    'results': received_ser.data,
                },
            },
        }, status=status.HTTP_200_OK)


class SentInterestsView(APIView):
    """
    GET /api/v1/interests/sent/
    Paginated list of interests sent by the current user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            page = int(request.query_params.get('page', 1) or 1)
        except ValueError:
            page = 1
        try:
            limit = int(request.query_params.get('limit', 10) or 10)
        except ValueError:
            limit = 10
        page = max(1, page)
        limit = max(1, min(limit, 50))

        qs = Interest.objects.filter(sender=user).select_related('receiver').order_by('-created_at')
        total = qs.count()
        start = (page - 1) * limit
        end = start + limit
        page_qs = qs[start:end]

        ser = InterestListSerializer(
            page_qs, many=True, context={'direction': 'sent', 'request': request}
        )
        return Response({
            'success': True,
            'data': {
                'total': total,
                'results': ser.data,
            },
        }, status=status.HTTP_200_OK)


class ReceivedInterestsView(APIView):
    """
    GET /api/v1/interests/received/
    Paginated list of interests received by the current user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            page = int(request.query_params.get('page', 1) or 1)
        except ValueError:
            page = 1
        try:
            limit = int(request.query_params.get('limit', 10) or 10)
        except ValueError:
            limit = 10
        page = max(1, page)
        limit = max(1, min(limit, 50))

        qs = Interest.objects.filter(receiver=user).select_related('sender').order_by('-created_at')
        total = qs.count()
        start = (page - 1) * limit
        end = start + limit
        page_qs = qs[start:end]

        ser = InterestListSerializer(
            page_qs, many=True, context={'direction': 'received', 'request': request}
        )
        return Response({
            'success': True,
            'data': {
                'total': total,
                'results': ser.data,
            },
        }, status=status.HTTP_200_OK)


class RespondInterestView(APIView):
    """
    POST /api/v1/interests/respond/
    Body: { "interest_id": 15, "action": "accept" | "reject" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        interest_id = request.data.get('interest_id')
        action = (request.data.get('action') or '').strip().lower()
        if not interest_id or action not in ('accept', 'reject'):
            return Response({
                'success': False,
                'error': {
                    'code': 400,
                    'message': 'Invalid request.',
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            interest = Interest.objects.select_related('receiver').get(pk=interest_id)
        except Interest.DoesNotExist:
            return Response({
                'success': False,
                'error': {
                    'code': 404,
                    'message': 'Interest not found.',
                },
            }, status=status.HTTP_404_NOT_FOUND)

        if interest.receiver_id != request.user.id:
            return Response({
                'success': False,
                'error': {
                    'code': 403,
                    'message': 'Permission denied.',
                },
            }, status=status.HTTP_403_FORBIDDEN)

        if action == 'accept':
            interest.status = Interest.STATUS_ACCEPTED
            msg = 'Interest accepted.'
        else:
            interest.status = Interest.STATUS_REJECTED
            msg = 'Interest rejected.'
        interest.save(update_fields=['status', 'updated_at'])

        return Response({'success': True, 'message': msg}, status=status.HTTP_200_OK)


class CancelInterestView(APIView):
    """
    POST /api/v1/interests/cancel/
    Body: { "interest_id": 15 }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        interest_id = request.data.get('interest_id')
        if not interest_id:
            return Response({
                'success': False,
                'error': {
                    'code': 400,
                    'message': 'Invalid request.',
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            interest = Interest.objects.select_related('sender').get(pk=interest_id)
        except Interest.DoesNotExist:
            return Response({
                'success': False,
                'error': {
                    'code': 404,
                    'message': 'Interest not found.',
                },
            }, status=status.HTTP_404_NOT_FOUND)

        if interest.sender_id != request.user.id:
            return Response({
                'success': False,
                'error': {
                    'code': 403,
                    'message': 'Permission denied.',
                },
            }, status=status.HTTP_403_FORBIDDEN)

        if interest.status != Interest.STATUS_PENDING:
            return Response({
                'success': False,
                'error': {
                    'code': 400,
                    'message': 'Only pending interests can be cancelled.',
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        interest.status = Interest.STATUS_CANCELLED
        interest.save(update_fields=['status', 'updated_at'])

        return Response({
            'success': True,
            'message': 'Interest cancelled successfully.',
        }, status=status.HTTP_200_OK)


class ChatPermissionView(APIView):
    """
    GET /api/v1/chat/permission/{matri_id}/
    Returns { "can_chat": true } only if plan allows and limit remaining.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'}
            }, status=status.HTTP_404_NOT_FOUND)

        # Require accepted interest before chat is allowed.
        if not has_accepted_interest_between(request.user, profile_user):
            return Response({
                'success': True,
                'data': {'can_chat': False}
            }, status=status.HTTP_200_OK)

        can_chat_flag, _ = can_chat(request.user)
        return Response({
            'success': True,
            'data': {'can_chat': can_chat_flag}
        }, status=status.HTTP_200_OK)


class ContactUnlockView(APIView):
    """
    POST /api/v1/contact/unlock/
    Body: { "matri_id": "AM100012" }
    Uses PlanLimitService.can_view_contact and consume_contact_view.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        matri_id = (request.data.get('matri_id') or '').strip()
        if not matri_id:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'matri_id is required.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        if is_plan_expired(request.user):
            return Response(plan_expired_response(request.user), status=status.HTTP_403_FORBIDDEN)

        try:
            target = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'}
            }, status=status.HTTP_404_NOT_FOUND)

        if target.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Cannot view your own contact details.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        can_view, _ = can_view_contact(request.user)
        if not can_view:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Upgrade plan to view contact'}
            }, status=status.HTTP_403_FORBIDDEN)

        PlanLimitService.consume_contact_view(request.user)

        return Response({
            'success': True,
            'data': {
                'phone': target.mobile or '',
                'email': target.email or '',
            },
        }, status=status.HTTP_200_OK)


class ChatStartView(APIView):
    """
    POST /api/v1/chat/start/
    Body: { "matri_id": \"AM100012\" }
    Checks chat limit via PlanLimitService.can_chat, decrements on success,
    and creates or returns a Conversation between the two users.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        matri_id = (request.data.get('matri_id') or '').strip()
        if not matri_id:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'matri_id is required.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        if is_plan_expired(request.user):
            return Response(plan_expired_response(request.user), status=status.HTTP_403_FORBIDDEN)

        try:
            other = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'}
            }, status=status.HTTP_404_NOT_FOUND)

        if other.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Cannot chat with yourself.'}
            }, status=status.HTTP_400_BAD_REQUEST)

        # Require accepted interest before starting a chat.
        if not has_accepted_interest_between(request.user, other):
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Please accept the interest request to start chat.'}
            }, status=status.HTTP_403_FORBIDDEN)

        can_chat_flag, _ = can_chat(request.user)
        if not can_chat_flag:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Upgrade plan to chat'}
            }, status=status.HTTP_403_FORBIDDEN)

        # Ensure consistent ordering so unique constraint works (user1_id < user2_id)
        u1, u2 = (request.user, other) if request.user.pk < other.pk else (other, request.user)
        conv, created = Conversation.objects.get_or_create(user1=u1, user2=u2)

        if created:
            PlanLimitService.consume_chat(request.user)

        return Response({
            'success': True,
            'data': {
                'conversation_id': conv.id,
                'message': 'Chat started successfully',
            },
        }, status=status.HTTP_200_OK)


class MyPlanView(APIView):
    """
    GET /api/v1/my/plan/  — Returns current plan status and remaining limits.
    DELETE /api/v1/my/plan/  — Removes your plan purchase (UserPlan + your plan transactions).
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'delete', 'head', 'options']

    def get(self, request):
        data = get_plan_info_for_response(request.user)
        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        user = request.user
        deleted_plan = None
        try:
            up = UserPlan.objects.get(user=user)
            deleted_plan = up.plan.name
            up.delete()
        except UserPlan.DoesNotExist:
            pass
        Transaction.objects.filter(user=user).delete()
        return Response({
            'success': True,
            'message': 'Plan purchase removed.' if deleted_plan else 'No plan to remove.',
            'data': {'removed_plan': deleted_plan},
        }, status=status.HTTP_200_OK)
