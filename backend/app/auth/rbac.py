from __future__ import annotations
import hashlib
import hmac
import os
import secrets
from enum import Enum
from typing import Dict, List, Optional, Set
from fastapi import Header, HTTPException
from pydantic import BaseModel

MAX_ACTIVE_TOKENS = 1000


class OperatorRole(str, Enum):
    ADMINISTRATOR = "administrator"
    OPERATIONS_COMMANDER = "operations_commander"
    COUNTRY_COMMANDER = "country_commander"
    FLEET_OPERATOR = "fleet_operator"
    MEDICAL_COORDINATOR = "medical_coordinator"
    ANALYST = "analyst"
    VIEWER = "viewer"


ROLE_PERMISSIONS: Dict[OperatorRole, Set[str]] = {
    OperatorRole.ADMINISTRATOR: {
        "read:all", "write:countries", "write:disasters", "write:drones",
        "write:swarms", "write:ambulances", "write:logistics", "write:approvals",
        "execute:operations", "admin:reset", "admin:emergency_stop", "export:all",
    },
    OperatorRole.OPERATIONS_COMMANDER: {
        "read:all", "write:disasters", "write:drones", "write:swarms",
        "write:ambulances", "write:logistics", "write:approvals",
        "execute:operations", "admin:emergency_stop", "export:all",
    },
    OperatorRole.COUNTRY_COMMANDER: {
        "read:all", "write:countries", "write:disasters", "write:approvals",
        "execute:operations", "export:all",
    },
    OperatorRole.FLEET_OPERATOR: {
        "read:all", "write:drones", "write:swarms", "execute:operations",
    },
    OperatorRole.MEDICAL_COORDINATOR: {
        "read:all", "write:ambulances", "write:logistics", "execute:operations",
    },
    OperatorRole.ANALYST: {
        "read:all", "export:all",
    },
    OperatorRole.VIEWER: {
        "read:all",
    },
}


class OperatorSession(BaseModel):
    username: str
    role: OperatorRole
    display_name: str
    country_scope: Optional[str] = None
    permissions: List[str]
    must_change_password: bool = False


class AuthService:
    """Lightweight RBAC service for local demo and shared command deployments."""

    def __init__(self) -> None:
        self._secret = os.getenv("BACKEND_SECRET", "quantum-rescue-local-dev-secret")
        default_admin_pw = os.getenv("QR_DEMO_ADMIN_PASSWORD", "quantum-admin-local")
        self._users: Dict[str, Dict[str, str]] = {
            "admin": {
                "password_hash": self._hash_pw(default_admin_pw),
                "role": OperatorRole.ADMINISTRATOR.value,
                "display_name": "Global Administrator (Local Demo)",
                "must_change_password": "true",
            },
            "ops": {
                "password_hash": self._hash_pw("quantum-ops-local"),
                "role": OperatorRole.OPERATIONS_COMMANDER.value,
                "display_name": "Operations Commander",
                "must_change_password": "false",
            },
            "fleet": {
                "password_hash": self._hash_pw("quantum-fleet-local"),
                "role": OperatorRole.FLEET_OPERATOR.value,
                "display_name": "Fleet Operator",
                "must_change_password": "false",
            },
            "medical": {
                "password_hash": self._hash_pw("quantum-med-local"),
                "role": OperatorRole.MEDICAL_COORDINATOR.value,
                "display_name": "Medical Coordinator",
                "must_change_password": "false",
            },
            "analyst": {
                "password_hash": self._hash_pw("quantum-analyst-local"),
                "role": OperatorRole.ANALYST.value,
                "display_name": "Operations Analyst",
                "must_change_password": "false",
            },
        }
        self._tokens: Dict[str, OperatorSession] = {}

    def _hash_pw(self, password: str) -> str:
        return hmac.new(self._secret.encode(), password.encode(), hashlib.sha256).hexdigest()

    def login(self, username: str, password: str) -> Dict[str, object]:
        record = self._users.get(username)
        if not record or not hmac.compare_digest(record["password_hash"], self._hash_pw(password)):
            raise HTTPException(status_code=401, detail="Invalid operator credentials")
        role = OperatorRole(record["role"])
        token = f"qr_{secrets.token_hex(16)}"
        session = OperatorSession(
            username=username,
            role=role,
            display_name=record["display_name"],
            permissions=sorted(ROLE_PERMISSIONS[role]),
            must_change_password=record["must_change_password"] == "true",
        )
        if len(self._tokens) >= MAX_ACTIVE_TOKENS:
            oldest_token = next(iter(self._tokens))
            del self._tokens[oldest_token]
        self._tokens[token] = session
        return {"token": token, "session": session}

    def resolve_session(
        self,
        authorization: Optional[str] = None,
        x_operator_role: Optional[str] = None,
    ) -> OperatorSession:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            if token in self._tokens:
                return self._tokens[token]
        if x_operator_role:
            try:
                role = OperatorRole(x_operator_role.lower())
            except ValueError:
                role = OperatorRole.VIEWER
            return OperatorSession(
                username=f"local_{role.value}",
                role=role,
                display_name=role.value.replace("_", " ").title(),
                permissions=sorted(ROLE_PERMISSIONS[role]),
                must_change_password=False,
            )
        # Local single-operator demo defaults to Administrator so all 3 local frontends work seamlessly
        return OperatorSession(
            username="admin",
            role=OperatorRole.ADMINISTRATOR,
            display_name="Global Administrator (Local Demo)",
            permissions=sorted(ROLE_PERMISSIONS[OperatorRole.ADMINISTRATOR]),
            must_change_password=True,
        )

    def check_permission(self, session: OperatorSession, permission: str) -> None:
        if permission not in session.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{session.role.value}' lacks required permission '{permission}'",
            )


auth_service = AuthService()


def get_current_operator(
    authorization: Optional[str] = Header(default=None),
    x_operator_role: Optional[str] = Header(default=None),
) -> OperatorSession:
    return auth_service.resolve_session(authorization=authorization, x_operator_role=x_operator_role)
