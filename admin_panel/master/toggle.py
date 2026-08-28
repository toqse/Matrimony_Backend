from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser


def _error(message: str, code: int, include_message: bool = False):
    body = {"success": False, "error": {"code": code, "message": message}}
    if include_message:
        body["message"] = message
    return Response(body, status=code)


class MasterToggleStatusAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    model = None
    not_found_message = "Record not found."
    include_message = False

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get_object(self, pk: int):
        return self.model.objects.filter(pk=pk).first()

    def serialize(self, obj):
        raise NotImplementedError

    def cascade_deactivate(self, obj):
        pass

    def invalidate(self, obj, activating: bool):
        pass

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403, self.include_message)
        obj = self.get_object(pk)
        if not obj:
            return _error(self.not_found_message, 404, self.include_message)

        activating = not obj.is_active
        with transaction.atomic():
            obj.is_active = activating
            obj.save(update_fields=["is_active", "updated_at"])
            if not activating:
                self.cascade_deactivate(obj)

        self.invalidate(obj, activating)
        payload = {"success": True, "data": self.serialize(obj)}
        if self.include_message:
            label = self.model._meta.verbose_name
            payload["message"] = f"{label.capitalize()} {'activated' if activating else 'deactivated'} successfully"
        return Response(payload)
