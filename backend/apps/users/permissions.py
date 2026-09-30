from rest_framework import permissions

class IsPlatformAdmin(permissions.BasePermission):
    """
    Allows access only to authenticated platform administrators.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            getattr(request.user, 'role', None) == 'admin'
            or request.user.is_staff
            or request.user.is_superuser
        )


class IsTeacher(permissions.BasePermission):
    """
    Allows access only to authenticated teachers.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            getattr(request.user, 'role', None) == 'teacher'
            or hasattr(request.user, 'teacher_profile')
            or request.user.is_staff
        )


class IsStudent(permissions.BasePermission):
    """
    Allows access only to authenticated students.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            getattr(request.user, 'role', None) == 'student'
            or request.user.is_staff
        )


class IsTeacherOrAdmin(permissions.BasePermission):
    """
    Allows access to either teachers or platform admins.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            getattr(request.user, 'role', None) in ['teacher', 'admin']
            or hasattr(request.user, 'teacher_profile')
            or request.user.is_staff
            or request.user.is_superuser
        )
