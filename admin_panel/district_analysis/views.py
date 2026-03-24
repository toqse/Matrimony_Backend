from __future__ import annotations

from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import District
from plans.models import Transaction
from profiles.models import UserLocation


def _error(message: str, code: int = 400):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == AdminUser.ROLE_ADMIN


def _district_rows(state_id: str | None, sort_by: str | None) -> tuple[list[dict], str | None]:
    district_qs = District.objects.filter(is_active=True, state__is_active=True).values("id", "name", "state_id")
    if state_id:
        district_qs = district_qs.filter(state_id=state_id)
    districts = list(district_qs.order_by("name"))
    district_ids = [d["id"] for d in districts]

    if not district_ids:
        return [], None

    registrations_rows = (
        UserLocation.objects.filter(user__role="user", district_id__in=district_ids)
        .values("district_id")
        .annotate(count=Count("user_id", distinct=True))
        .order_by()
    )
    registrations_by_district = {r["district_id"]: int(r["count"] or 0) for r in registrations_rows}

    paid_rows = (
        Transaction.objects.filter(
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            payment_status=Transaction.STATUS_SUCCESS,
            user__role="user",
            user__user_location__district_id__in=district_ids,
        )
        .values("user__user_location__district_id")
        .annotate(count=Count("user_id", distinct=True))
        .order_by()
    )
    paid_by_district = {r["user__user_location__district_id"]: int(r["count"] or 0) for r in paid_rows}

    active_rows = (
        User.objects.filter(
            role="user",
            is_active=True,
            is_registration_profile_completed=True,
            user_location__district_id__in=district_ids,
        )
        .values("user_location__district_id")
        .annotate(count=Count("id", distinct=True))
        .order_by()
    )
    active_by_district = {r["user_location__district_id"]: int(r["count"] or 0) for r in active_rows}

    rows = []
    for district in districts:
        district_id = district["id"]
        registrations = registrations_by_district.get(district_id, 0)
        paid_users = paid_by_district.get(district_id, 0)
        active_profiles = active_by_district.get(district_id, 0)
        # Hide districts with no data at all in both list and geojson outputs.
        if registrations == 0 and paid_users == 0 and active_profiles == 0:
            continue
        conversion_rate = round((paid_users / registrations) * 100, 1) if registrations else 0.0
        rows.append(
            {
                "district": district["name"],
                "district_id": district_id,
                "state_id": district["state_id"],
                "registrations": registrations,
                "paid_users": paid_users,
                "active_profiles": active_profiles,
                "conversion_rate": conversion_rate,
            }
        )

    if sort_by:
        if sort_by not in {"registrations", "conversion_rate"}:
            return [], "Invalid sort_by. Use registrations or conversion_rate"
        rows.sort(key=lambda item: item[sort_by], reverse=True)
    else:
        rows.sort(key=lambda item: item["district"])

    return rows, None


class DistrictAnalysisListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return _error("Insufficient permissions", 403)
        state_id = (request.query_params.get("state_id") or "").strip() or None
        sort_by = (request.query_params.get("sort_by") or "").strip() or None
        rows, err = _district_rows(state_id=state_id, sort_by=sort_by)
        if err:
            return _error(err, 400)
        return Response({"success": True, "data": rows})


class DistrictAnalysisGeoJSONAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return _error("Insufficient permissions", 403)
        state_id = (request.query_params.get("state_id") or "").strip() or None
        rows, _ = _district_rows(state_id=state_id, sort_by=None)
        features = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": row,
                }
            )
        return Response(
            {
                "success": True,
                "data": {
                    "type": "FeatureCollection",
                    "features": features,
                },
            }
        )
