"""
Plan and interest APIs: Admin Plan CRUD, List Plans, Purchase, Send Interest, Chat Permission, My Plan.
"""
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import JSONParser
from rest_framework.viewsets import ModelViewSet

from accounts.models import User
from core.phone import to_e164_display
from profiles.models import UserProfile
from core.permissions import IsAdmin
from user_settings.models import UserSettings
from django.db import transaction
from .models import Interest, Plan, ProfileView as ProfileViewModel, ServiceCharge, UserPlan, Transaction, Conversation
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
    activate_plan_purchase,
    pay_remaining_service_charge,
    plan_purchase_response_data,
    compute_service_charge_remaining,
    get_plan_info_for_response,
    has_unlocked_profile,
    is_plan_expired,
    plan_expired_response,
    get_user_plan_status,
    has_accepted_interest_between,
)


def _parse_page_params(
    request,
    page_param='page',
    page_size_param='page_size',
    limit_param='limit',
    default_page_size=10,
    max_page_size=50
):
    try:
        page = int(request.query_params.get(page_param, 1) or 1)
    except (TypeError, ValueError):
        page = 1

    raw_page_size = request.query_params.get(page_size_param)
    if raw_page_size is None:
        raw_page_size = request.query_params.get(limit_param, default_page_size)
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = default_page_size

    page = max(1, page)
    page_size = max(1, min(max_page_size, page_size))
    return page, page_size


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
            plan_price = plan.price or Decimal('0')
            out.append({
                'id': plan.id,
                'name': plan.name,
                'price': float(plan_price),
                'service_charge': float(service_charge),
                'total_price': float(total),
                'first_payment': float(plan_price),
                'service_charge_remaining': float(max(total, Decimal('0'))),
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


class WebsitePlanListView(APIView):
    """
    GET /api/v1/website/plans/
    Public plan list for website (no token required).
    Returns active plans and pricing breakdown for each gender.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by('price')
        service_charges = {
            row.gender: row.amount for row in ServiceCharge.objects.all()
        }

        out = []
        for plan in plans:
            price = plan.price or Decimal('0')
            male_sc = service_charges.get('M', Decimal('0'))
            female_sc = service_charges.get('F', Decimal('0'))
            other_sc = service_charges.get('O', Decimal('0'))

            out.append({
                'id': plan.id,
                'name': plan.name,
                'price': float(price),
                'duration_days': plan.duration_days,
                'profile_view_limit': plan.profile_view_limit,
                'interest_limit': plan.interest_limit,
                'chat_limit': plan.chat_limit,
                'horoscope_match_limit': plan.horoscope_match_limit,
                'contact_view_limit': plan.contact_view_limit,
                'description': plan.description or '',
                'service_charge': {
                    'male': float(male_sc),
                    'female': float(female_sc),
                    'other': float(other_sc),
                },
                'total_price': {
                    'male': float(male_sc + price),
                    'female': float(female_sc + price),
                    'other': float(other_sc + price),
                },
            })

        return Response({
            'success': True,
            'data': {
                'plans': out,
            },
        }, status=status.HTTP_200_OK)


ONLINE_PAYMENT_METHODS = frozenset({
    Transaction.PAYMENT_RAZORPAY,
    Transaction.PAYMENT_STRIPE,
    Transaction.PAYMENT_UPI,
})


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

        if payment_method in ONLINE_PAYMENT_METHODS:
            return Response({
                'success': False,
                'error': {
                    'code': 400,
                    'message': (
                        'Online payments must use Razorpay checkout. '
                        'POST /api/v1/plans/order/ then /api/v1/plans/verify/.'
                    ),
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        plan = Plan.objects.get(pk=plan_id)
        user = request.user

        _, txn, extra = activate_plan_purchase(
            user=user,
            plan=plan,
            payment_option=payment_option,
            payment_method=payment_method,
        )

        return Response({
            'success': True,
            'message': extra.pop('message'),
            'data': plan_purchase_response_data(txn, plan, extra),
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

        if payment_method in ONLINE_PAYMENT_METHODS:
            return Response({
                'success': False,
                'error': {
                    'code': 400,
                    'message': (
                        'Online payments must use Razorpay checkout. '
                        'POST /api/v1/plans/pay-remaining-service/order/ then .../verify/.'
                    ),
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            _, remaining = compute_service_charge_remaining(user)
        except UserPlan.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'No active plan found. Purchase a plan first.'},
            }, status=status.HTTP_404_NOT_FOUND)

        if remaining <= 0:
            return Response({
                'success': True,
                'message': 'No remaining service charge to pay.',
                'data': {'amount_paid': 0, 'service_charge_remaining': 0},
            }, status=status.HTTP_200_OK)

        _, txn, amount_paid = pay_remaining_service_charge(
            user=user,
            payment_method=payment_method,
        )
        return Response({
            'success': True,
            'message': 'Remaining service charge paid successfully.',
            'data': {
                'transaction_id': txn.id,
                'amount_paid': float(amount_paid),
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

        # Mutual interest: they already sent you a pending request; reciprocating accepts both sides.
        incoming = Interest.objects.filter(
            sender=receiver,
            receiver=request.user,
            status=Interest.STATUS_PENDING,
        ).first()
        if incoming:
            with transaction.atomic():
                incoming.status = Interest.STATUS_ACCEPTED
                incoming.save(update_fields=['status', 'updated_at'])
                PlanLimitService.consume_interest(request.user)
            return Response({
                'success': True,
                'message': 'You both expressed interest. Connection accepted.',
                'data': {'status': Interest.STATUS_ACCEPTED, 'interest_id': incoming.id},
            }, status=status.HTTP_200_OK)

        interest, created = Interest.objects.get_or_create(
            sender=request.user,
            receiver=receiver,
            defaults={'status': Interest.STATUS_PENDING}
        )
        if not created:
            # Allow re-sending after sender cancelled or receiver rejected.
            # Re-activate the same row back to pending so match list flags
            # (is_interest_sent / interest_status) stay consistent.
            if interest.status in (Interest.STATUS_CANCELLED, Interest.STATUS_REJECTED):
                interest.status = Interest.STATUS_PENDING
                interest.save(update_fields=['status', 'updated_at'])
                PlanLimitService.consume_interest(request.user)
                return Response({
                    'success': True,
                    'message': 'Interest sent successfully.',
                    'data': {'status': Interest.STATUS_PENDING},
                }, status=status.HTTP_200_OK)
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


_INTEREST_RECEIVER_SELECT = (
    'receiver',
    'receiver__user_location',
    'receiver__user_location__city',
    'receiver__user_location__state',
    'receiver__user_education',
    'receiver__user_education__highest_education',
    'receiver__user_education__occupation',
    'receiver__user_photos',
)
_INTEREST_SENDER_SELECT = (
    'sender',
    'sender__user_location',
    'sender__user_location__city',
    'sender__user_location__state',
    'sender__user_education',
    'sender__user_education__highest_education',
    'sender__user_education__occupation',
    'sender__user_photos',
)


class MyInterestsView(APIView):
    """
    GET /api/v1/interests/my/
    Returns interests sent and received by the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        sent_page, sent_page_size = _parse_page_params(
            request,
            page_param='sent_page',
            page_size_param='sent_page_size',
            limit_param='sent_limit',
            default_page_size=10,
            max_page_size=50,
        )
        received_page, received_page_size = _parse_page_params(
            request,
            page_param='received_page',
            page_size_param='received_page_size',
            limit_param='received_limit',
            default_page_size=10,
            max_page_size=50,
        )

        sent_qs = Interest.objects.filter(sender=user).select_related(*_INTEREST_RECEIVER_SELECT).order_by('-created_at')
        received_qs = Interest.objects.filter(receiver=user).select_related(*_INTEREST_SENDER_SELECT).order_by('-created_at')
        sent_total = sent_qs.count()
        received_total = received_qs.count()

        sent_start = (sent_page - 1) * sent_page_size
        received_start = (received_page - 1) * received_page_size
        sent_page_qs = sent_qs[sent_start:sent_start + sent_page_size]
        received_page_qs = received_qs[received_start:received_start + received_page_size]

        sent_ser = InterestListSerializer(
            sent_page_qs, many=True, context={'direction': 'sent', 'request': request}
        )
        received_ser = InterestListSerializer(
            received_page_qs, many=True, context={'direction': 'received', 'request': request}
        )

        return Response({
            'success': True,
            'data': {
                'sent': {
                    'total': sent_total,
                    'page': sent_page,
                    'page_size': sent_page_size,
                    'limit': sent_page_size,
                    'results': sent_ser.data,
                },
                'received': {
                    'total': received_total,
                    'page': received_page,
                    'page_size': received_page_size,
                    'limit': received_page_size,
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
        page, page_size = _parse_page_params(
            request, default_page_size=10, max_page_size=50
        )

        qs = Interest.objects.filter(sender=user).select_related(*_INTEREST_RECEIVER_SELECT).order_by('-created_at')
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        page_qs = qs[start:end]

        ser = InterestListSerializer(
            page_qs, many=True, context={'direction': 'sent', 'request': request}
        )
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'limit': page_size,
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
        page, page_size = _parse_page_params(
            request, default_page_size=10, max_page_size=50
        )

        qs = Interest.objects.filter(receiver=user).select_related(*_INTEREST_SENDER_SELECT).order_by('-created_at')
        total = qs.count()
        start = (page - 1) * page_size
        end = start + page_size
        page_qs = qs[start:end]

        ser = InterestListSerializer(
            page_qs, many=True, context={'direction': 'received', 'request': request}
        )
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'limit': page_size,
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

        if action == 'accept' and get_user_plan_status(request.user) != 'active':
            return Response(plan_expired_response(request.user), status=status.HTTP_403_FORBIDDEN)

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
    If the viewer has not opened this profile before, also records ProfileView and
    consume_profile_view (blocked with 403 when profile view quota is exhausted).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        from profiles.views import _build_profile_data_for_user

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

        target_profile = UserProfile.objects.filter(user=target).first()
        if not target_profile:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'}
            }, status=status.HTTP_404_NOT_FOUND)

        already_unlocked = has_unlocked_profile(request.user, target_profile)
        if not already_unlocked:
            can_profile, _ = PlanLimitService.can_view_profile(request.user)
            if not can_profile:
                return Response({
                    'success': False,
                    'error': {
                        'code': 403,
                        'message': 'Upgrade plan to view profile',
                    }
                }, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            PlanLimitService.consume_contact_view(request.user)
            _, _, newly_unlocked = ProfileViewModel.touch(
                request.user, target_profile, unlock=True
            )
            if newly_unlocked:
                PlanLimitService.consume_profile_view(request.user)

        profile = _build_profile_data_for_user(
            target, request=request, include_contact=True, include_family=True
        )

        return Response({
            'success': True,
            'data': {
                'phone': to_e164_display(target.mobile or ''),
                'email': target.email or '',
                'is_viewed_by_me': True,
                'profile': profile,
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

        if get_user_plan_status(request.user) != 'active':
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
                'error': {'code': 403, 'message': 'Interest is not Accepted by the other user.'}
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
