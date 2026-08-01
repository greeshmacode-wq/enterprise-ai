from rest_framework.permissions import BasePermission
from apps.accounts.models import User


class HasRole(BasePermission):
    """Grants access only to requests from users whose role is in allowed_roles."""

    allowed_roles: frozenset[str] = frozenset()

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in self.allowed_roles
        )


class IsAdmin(HasRole):
    allowed_roles = frozenset({User.RoleChoices.ADMIN})


class IsManagerOrAbove(HasRole):
    allowed_roles = frozenset({User.RoleChoices.ADMIN, User.RoleChoices.MANAGER})


class IsEmployeeOrAbove(HasRole):
    allowed_roles = frozenset({
        User.RoleChoices.ADMIN,
        User.RoleChoices.MANAGER,
        User.RoleChoices.EMPLOYEE,
    })
