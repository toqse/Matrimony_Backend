"""
Reusable DRF permission classes: roles, branch-scoped, subscription-gated.
"""
from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'admin'


class ReadOnlyOrAdmin(permissions.BasePermission):
    """Allow anyone to read (GET, HEAD, OPTIONS); only admin can write (POST, PUT, PATCH, DELETE)."""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated and request.user.role == 'admin'


class IsBranchManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'branch_manager'


class IsStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ('staff', 'branch_manager', 'admin')


class IsStaffOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in ('staff', 'admin', 'branch_manager')


class IsUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'user'


class BranchScoped(permissions.BasePermission):
    """
    Placeholder: staff/branch APIs removed. Admin can access all; others denied for branch-scoped objects.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'admin':
            return True
        return False


class IsSubscribed(permissions.BasePermission):
    """Allow only if user has active subscription."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(request.user, 'is_subscribed', False)
