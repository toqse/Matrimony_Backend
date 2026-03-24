from io import BytesIO

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from master.models import Branch as MasterBranch

from .models import StaffProfile
from .serializers import StaffSerializer


def _escape_pdf_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    y_start = 780
    line_gap = 18
    text_lines = ["BT", "/F1 12 Tf", f"50 {y_start} Td"]
    first = True
    for line in lines:
        if not first:
            text_lines.append(f"0 -{line_gap} Td")
        text_lines.append(f"({_escape_pdf_text(line)}) Tj")
        first = False
    text_lines.append("ET")
    stream = "\n".join(text_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objects.append(
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)
    xref_pos = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.write(f"{off:010d} 00000 n \n".encode())
    pdf.write(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
        ).encode()
    )
    return pdf.getvalue()


class StaffViewSet(viewsets.ModelViewSet):
    serializer_class = StaffSerializer
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _manager_branch_code(self):
        user = self.request.user
        if getattr(user, "role", None) != AdminUser.ROLE_BRANCH_MANAGER:
            return None
        return (
            MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
            .values_list("code", flat=True)
            .first()
        )

    def get_queryset(self):
        qs = (
            StaffProfile.objects.filter(is_deleted=False)
            .select_related("branch", "admin_user")
            .order_by("-created_at")
        )
        user = self.request.user
        if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = self._manager_branch_code()
            if manager_code:
                qs = qs.filter(branch__code=manager_code)
            else:
                qs = qs.none()

        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(emp_code__icontains=search)
                | Q(name__icontains=search)
                | Q(designation__icontains=search)
                | Q(branch__name__icontains=search)
            )

        branch_id = self.request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        status_param = (self.request.query_params.get("status") or "").lower().strip()
        if status_param in {"active", "inactive"}:
            qs = qs.filter(is_active=(status_param == "active"))

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            paged = self.get_paginated_response(ser.data).data
            return Response({"success": True, "data": paged})
        ser = self.get_serializer(qs, many=True)
        return Response({"success": True, "data": {"results": ser.data}})

    def _deny_if_wrong_branch(self, branch_id):
        user = self.request.user
        if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = self._manager_branch_code()
            staff_branch_code = (
                StaffProfile.objects.filter(branch_id=branch_id).values_list("branch__code", flat=True).first()
            )
            if not manager_code or manager_code != staff_branch_code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
        return None

    def create(self, request, *args, **kwargs):
        requested_role = request.data.get("role") or AdminUser.ROLE_STAFF
        if (
            requested_role == AdminUser.ROLE_BRANCH_MANAGER
            and getattr(request.user, "role", None) != AdminUser.ROLE_ADMIN
        ):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Only admin can create branch manager"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if getattr(request.user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            branch_id = request.data.get("branch")
            requested_code = (
                Branch.objects.filter(pk=branch_id)
                .values_list("code", flat=True)
                .first()
            )
            manager_code = self._manager_branch_code()
            if not manager_code or manager_code != requested_code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        staff = ser.save()
        return Response({"success": True, "data": self.get_serializer(staff).data}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        staff = self.get_object()
        data = self.get_serializer(staff).data
        target = int(staff.monthly_target or 0)
        achieved = int(staff.achieved_target or 0)
        data["performance"] = {
            "achieved": achieved,
            "target": target,
            "percentage": round((achieved / target) * 100, 2) if target else 0,
        }
        return Response({"success": True, "data": data})

    def partial_update(self, request, *args, **kwargs):
        staff = self.get_object()
        if "branch" in request.data:
            try:
                branch_id = int(request.data.get("branch"))
            except (TypeError, ValueError):
                branch_id = None
            deny = self._deny_if_wrong_branch(branch_id)
            if deny:
                return deny
        ser = self.get_serializer(staff, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        staff = ser.save()
        return Response({"success": True, "data": self.get_serializer(staff).data})

    def destroy(self, request, *args, **kwargs):
        staff = self.get_object()
        staff.is_active = False
        staff.is_deleted = True
        staff.save(update_fields=["is_active", "is_deleted", "updated_at"])
        staff.admin_user.is_active = False
        staff.admin_user.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        staff = self.get_object()
        staff.is_active = not staff.is_active
        staff.save(update_fields=["is_active", "updated_at"])
        staff.admin_user.is_active = staff.is_active
        staff.admin_user.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True, "status": "active" if staff.is_active else "inactive"})

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None):
        staff = self.get_object()
        lines = [
            "Staff Performance Report",
            f"Employee Code: {staff.emp_code}",
            f"Name: {staff.name}",
            f"Branch: {staff.branch.name}",
            f"Designation: {staff.designation}",
            f"Status: {'Active' if staff.is_active else 'Inactive'}",
            f"Monthly Target: {staff.monthly_target}",
            f"Achieved: {staff.achieved_target}",
            f"Commission %: {staff.commission_rate}",
            f"Basic Salary: {staff.basic_salary}",
        ]
        pdf_bytes = _build_simple_pdf(lines)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{staff.emp_code}_report.pdf"'
        return resp


class BranchStaffListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "role", None) not in {AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_ADMIN}:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = StaffProfile.objects.filter(is_deleted=False).select_related("branch")
        if request.user.role == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = (
                MasterBranch.objects.filter(pk=getattr(request.user, "branch_id", None))
                .values_list("code", flat=True)
                .first()
            )
            qs = qs.filter(branch__code=manager_code) if manager_code else qs.none()
        elif request.query_params.get("branch_id"):
            qs = qs.filter(branch_id=request.query_params.get("branch_id"))
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(emp_code__icontains=search) | Q(name__icontains=search) | Q(designation__icontains=search))
        status_param = (request.query_params.get("status") or "").lower().strip()
        if status_param in {"active", "inactive"}:
            qs = qs.filter(is_active=(status_param == "active"))
        ser = StaffSerializer(qs.order_by("-created_at"), many=True)
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})
