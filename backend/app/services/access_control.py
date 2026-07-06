from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


SENSITIVE_GRAPH_SCOPE = "commercial_graph:read"
DEFAULT_JWT_ISSUER = "vietsupply-dev"
DEFAULT_JWT_AUDIENCE = "vietsupply-api"
DEFAULT_JWT_SECRET = "dev-secret-change-me"
DEFAULT_AUTH_PROVIDER = "dev_jwt"
VALID_APP_MODES = {"demo", "pilot", "production"}


class AccessDeniedError(PermissionError):
    def __init__(self, code: str, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class JwtVerificationError(AccessDeniedError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=401)


@dataclass(frozen=True)
class Membership:
    organization_id: str
    role: str
    status: str = "active"


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    action: str
    effect: str
    reason: str
    resource_type: str = "unknown"
    resource_id: str | None = None
    data_classification: str | None = None


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    organization_id: str
    actor_id: str
    actor_role: str
    purpose: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    memberships: tuple[Membership, ...] = field(default_factory=tuple)
    roles: frozenset[str] = field(default_factory=frozenset)
    request_id: str = field(default_factory=lambda: f"req-{uuid4().hex[:12]}")
    auth_assurance: str = "demo-header"
    token_subject: str | None = None
    app_mode: str = "demo"

    def __post_init__(self) -> None:
        if not self.roles:
            object.__setattr__(self, "roles", frozenset({self.actor_role}))
        if not self.memberships and self.organization_id:
            object.__setattr__(
                self,
                "memberships",
                (Membership(organization_id=self.organization_id, role=self.actor_role),),
            )

    @classmethod
    def demo(cls) -> "RequestContext":
        return cls(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="demo-user",
            actor_role="demo_operator",
            purpose="demo_view",
            scopes=frozenset({"demo:read"}),
            roles=frozenset({"demo_operator"}),
            memberships=(Membership("org-demo", "demo_operator"),),
            auth_assurance="demo-header",
            app_mode="demo",
        )

    @classmethod
    def authorized_demo(cls) -> "RequestContext":
        return cls(
            tenant_id="tenant-demo",
            organization_id="org-demo",
            actor_id="demo-admin",
            actor_role="demo_admin",
            purpose="authorized_network_review",
            scopes=frozenset({"demo:read", SENSITIVE_GRAPH_SCOPE, "policy:override"}),
            roles=frozenset({"demo_admin", "reviewer", "network_analyst", "lender"}),
            memberships=(Membership("org-demo", "demo_admin"),),
            auth_assurance="demo-header",
            app_mode="demo",
        )

    @property
    def organization_ids(self) -> frozenset[str]:
        return frozenset(item.organization_id for item in self.memberships if item.status == "active")

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    def is_demo_actor(self) -> bool:
        return self.app_mode == "demo" and self.has_role("demo_operator", "demo_admin")


def current_app_mode() -> str:
    raw = os.getenv("APP_MODE", "demo").strip().lower()
    return raw if raw in VALID_APP_MODES else "demo"


def parse_scopes(raw_scopes: str | None) -> frozenset[str]:
    if not raw_scopes:
        return frozenset({"demo:read"})
    normalized = raw_scopes.replace(",", " ")
    return frozenset(scope.strip() for scope in normalized.split() if scope.strip())


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _json_b64(data: dict[str, Any]) -> str:
    return _base64url_encode(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def issue_dev_jwt(
    *,
    subject: str = "demo-user",
    tenant_id: str = "tenant-demo",
    organization_id: str = "BIZ-009",
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    purpose: str = "management_review",
    issuer: str | None = None,
    audience: str | None = None,
    secret: str | None = None,
    expires_in_seconds: int = 3600,
) -> str:
    """Create a local HS256 token for tests/dev only; production should use OIDC/JWKS."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": issuer or os.getenv("AUTH_JWT_ISSUER", DEFAULT_JWT_ISSUER),
        "aud": audience or os.getenv("AUTH_JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE),
        "sub": subject,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "roles": roles or ["sme_submitter"],
        "scopes": scopes or ["intake:write", "graph:read"],
        "purpose": purpose,
        "iat": now,
        "nbf": now - 5,
        "exp": now + expires_in_seconds,
    }
    signing_input = f"{_json_b64(header)}.{_json_b64(claims)}"
    digest = hmac.new(
        (secret or os.getenv("AUTH_JWT_SECRET", DEFAULT_JWT_SECRET)).encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(digest)}"


def verify_bearer_token(
    authorization: str | None,
    *,
    issuer: str | None = None,
    audience: str | None = None,
    secret: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise JwtVerificationError("AUTHORIZATION_REQUIRED", "Bearer token is required.")
    token = authorization.split(" ", maxsplit=1)[1].strip()
    active_provider = (provider or os.getenv("AUTH_PROVIDER", DEFAULT_AUTH_PROVIDER)).strip().lower()
    if active_provider == "oidc":
        return verify_oidc_token(token, issuer=issuer, audience=audience)
    if active_provider != "dev_jwt":
        raise JwtVerificationError("AUTH_PROVIDER_UNSUPPORTED", "Unsupported authentication provider.")
    return verify_dev_jwt_token(token, issuer=issuer, audience=audience, secret=secret)


def verify_dev_jwt_token(
    token: str,
    *,
    issuer: str | None = None,
    audience: str | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtVerificationError("JWT_MALFORMED", "JWT must have header, payload and signature.")
    header = json.loads(_base64url_decode(parts[0]))
    claims = json.loads(_base64url_decode(parts[1]))
    if header.get("alg") != "HS256":
        raise JwtVerificationError("JWT_ALGORITHM_UNSUPPORTED", "Only dev HS256 JWTs are supported by this adapter.")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(
        (secret or os.getenv("AUTH_JWT_SECRET", DEFAULT_JWT_SECRET)).encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    actual = _base64url_decode(parts[2])
    if not hmac.compare_digest(expected, actual):
        raise JwtVerificationError("JWT_SIGNATURE_INVALID", "JWT signature verification failed.")
    expected_issuer = issuer or os.getenv("AUTH_JWT_ISSUER", DEFAULT_JWT_ISSUER)
    expected_audience = audience or os.getenv("AUTH_JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE)
    if claims.get("iss") != expected_issuer:
        raise JwtVerificationError("JWT_ISSUER_INVALID", "JWT issuer is not trusted.")
    aud = claims.get("aud")
    if aud != expected_audience and expected_audience not in (aud if isinstance(aud, list) else []):
        raise JwtVerificationError("JWT_AUDIENCE_INVALID", "JWT audience is not accepted.")
    now = int(time.time())
    skew = int(os.getenv("AUTH_JWT_CLOCK_SKEW_SECONDS", "30"))
    if int(claims.get("exp", 0)) < now - skew:
        raise JwtVerificationError("JWT_EXPIRED", "JWT has expired.")
    if int(claims.get("nbf", 0)) > now + skew:
        raise JwtVerificationError("JWT_NOT_YET_VALID", "JWT is not valid yet.")
    if not claims.get("sub"):
        raise JwtVerificationError("JWT_SUBJECT_REQUIRED", "JWT subject is required.")
    claims["_auth_assurance"] = "jwt-dev-hs256"
    return claims


def verify_oidc_token(
    token: str,
    *,
    issuer: str | None = None,
    audience: str | None = None,
) -> dict[str, Any]:
    jwks_url = os.getenv("AUTH_JWKS_URL")
    if not jwks_url:
        raise JwtVerificationError("OIDC_JWKS_URL_REQUIRED", "AUTH_JWKS_URL is required for OIDC JWT verification.")
    try:
        import jwt  # type: ignore[import-not-found]
        from jwt import PyJWKClient  # type: ignore[import-not-found]
    except ImportError as exc:
        raise JwtVerificationError("OIDC_DEPENDENCY_MISSING", "Install PyJWT with crypto extras for OIDC JWT verification.") from exc
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience or os.getenv("AUTH_JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE),
            issuer=issuer or os.getenv("AUTH_JWT_ISSUER", DEFAULT_JWT_ISSUER),
            leeway=int(os.getenv("AUTH_JWT_CLOCK_SKEW_SECONDS", "30")),
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except Exception as exc:
        raise JwtVerificationError("OIDC_JWT_INVALID", f"OIDC JWT verification failed: {exc}") from exc
    if not isinstance(claims, dict):
        raise JwtVerificationError("OIDC_CLAIMS_INVALID", "OIDC JWT claims must decode to an object.")
    claims["_auth_assurance"] = "oidc-jwks"
    return claims


def _list_claim(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return parse_scopes(value)
    if isinstance(value, list):
        return frozenset(str(item) for item in value if str(item).strip())
    return frozenset()


def _memberships_from_claims(claims: dict[str, Any], fallback_org: str, roles: frozenset[str]) -> tuple[Membership, ...]:
    raw = claims.get("memberships")
    memberships: list[Membership] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("organization_id"):
                memberships.append(
                    Membership(
                        organization_id=str(item["organization_id"]),
                        role=str(item.get("role") or next(iter(roles), "sme_submitter")),
                        status=str(item.get("status") or "active"),
                    )
                )
            elif isinstance(item, str):
                memberships.append(Membership(organization_id=item, role=next(iter(roles), "sme_submitter")))
    if not memberships and fallback_org:
        memberships = [Membership(organization_id=fallback_org, role=role) for role in (roles or frozenset({"sme_submitter"}))]
    return tuple(memberships)


def context_from_token(
    claims: dict[str, Any],
    *,
    purpose: str | None = None,
    request_id: str | None = None,
    app_mode: str | None = None,
) -> RequestContext:
    roles = _list_claim(claims.get("roles")) or frozenset({"sme_submitter"})
    scopes = _list_claim(claims.get("scopes"))
    organization_id = str(claims.get("organization_id") or claims.get("org") or "")
    actor_role = str(claims.get("actor_role") or next(iter(roles)))
    return RequestContext(
        tenant_id=str(claims.get("tenant_id") or claims.get("tenant") or ""),
        organization_id=organization_id,
        actor_id=str(claims["sub"]),
        actor_role=actor_role,
        purpose=purpose or str(claims.get("purpose") or "management_review"),
        scopes=scopes,
        memberships=_memberships_from_claims(claims, organization_id, roles),
        roles=roles,
        request_id=request_id or f"req-{uuid4().hex[:12]}",
        auth_assurance=str(claims.get("_auth_assurance") or "jwt-dev-hs256"),
        token_subject=str(claims["sub"]),
        app_mode=app_mode or current_app_mode(),
    )


def context_from_headers(
    *,
    authorization: str | None = None,
    tenant_id: str | None = None,
    organization_id: str | None = None,
    actor_id: str | None = None,
    actor_role: str | None = None,
    purpose: str | None = None,
    scopes: str | None = None,
    request_id: str | None = None,
    app_mode: str | None = None,
) -> RequestContext:
    mode = app_mode or current_app_mode()
    if authorization:
        return context_from_token(
            verify_bearer_token(authorization),
            purpose=purpose,
            request_id=request_id,
            app_mode=mode,
        )
    if mode != "demo":
        raise JwtVerificationError("DEMO_HEADERS_DISABLED", "Pilot/production mode requires verified JWT auth.")
    demo = RequestContext.demo()
    role = actor_role or demo.actor_role
    return RequestContext(
        tenant_id=tenant_id or demo.tenant_id,
        organization_id=organization_id or demo.organization_id,
        actor_id=actor_id or demo.actor_id,
        actor_role=role,
        purpose=purpose or demo.purpose,
        scopes=parse_scopes(scopes),
        roles=frozenset({role}),
        memberships=(Membership(organization_id or demo.organization_id, role),),
        request_id=request_id or f"req-{uuid4().hex[:12]}",
        auth_assurance="demo-header",
        app_mode="demo",
    )


class PolicyService:
    CAPABILITY_ACTIONS: dict[str, str] = {
        "can_read_graph": "read_graph",
        "can_unmask_graph": "unmask_graph",
        "can_read_business": "read_business",
        "can_read_financials": "read_financials",
        "can_read_evidence": "read_evidence",
        "can_create_submission": "create_submission",
        "can_update_submission": "update_submission",
        "can_validate_submission": "validate_submission",
        "can_submit_submission": "submit_submission",
        "can_review_submission": "review_submission",
        "can_create_import_batch": "create_import_batch",
        "can_read_supply_map_registration": "read_supply_map_registration",
        "can_create_supply_map_registration": "create_supply_map_registration",
        "can_review_supply_map_registration": "review_supply_map_registration",
        "can_read_connection_request": "read_connection_request",
        "can_create_connection_request": "create_connection_request",
        "can_decide_connection_request": "decide_connection_request",
        "can_create_consent": "create_consent",
        "can_create_evidence_upload": "create_evidence_upload",
        "can_create_evidence_version": "create_evidence_version",
        "can_record_evidence_scan_result": "record_malware_scan_result",
        "can_read_invoice": "read_invoice",
        "can_register_invoice_claim": "register_invoice_claim",
        "can_transition_invoice_claim": "transition_invoice_claim",
        "can_read_risk_run": "read_risk_run",
        "can_read_match_run": "read_match_run",
        "can_read_scenario_run": "read_scenario_run",
        "can_read_audit": "read_audit",
    }
    ROLE_ACTIONS: dict[str, frozenset[str]] = {
        "demo_admin": frozenset({"*"}),
        "system_admin": frozenset({"*"}),
        "demo_operator": frozenset(
            {
                "read_graph",
                "read_business",
                "read_financials",
                "read_evidence",
                "create_submission",
                "update_submission",
                "validate_submission",
                "submit_submission",
                "review_submission",
                "create_import_batch",
                "create_connection_request",
                "decide_connection_request",
                "read_connection_request",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "review_supply_map_registration",
                "read_invoice",
                "create_consent",
                "revoke_consent",
                "create_evidence_upload",
                "create_evidence_version",
                "record_malware_scan_result",
                "grant_evidence_access",
                "revoke_evidence_access",
                "update_evidence_retention",
                "register_invoice_claim",
                "transition_invoice_claim",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
                "read_audit",
            }
        ),
        "sme_submitter": frozenset(
            {
                "read_business",
                "read_financials",
                "read_evidence",
                "create_submission",
                "update_submission",
                "validate_submission",
                "submit_submission",
                "create_import_batch",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "create_consent",
                "create_evidence_upload",
                "create_evidence_version",
                "read_invoice",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
            }
        ),
        "sme_user": frozenset(
            {
                "read_business",
                "read_financials",
                "read_evidence",
                "create_submission",
                "update_submission",
                "validate_submission",
                "submit_submission",
                "create_import_batch",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "create_consent",
                "create_evidence_upload",
                "create_evidence_version",
                "read_invoice",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
            }
        ),
        "org_admin": frozenset(
            {
                "read_business",
                "read_financials",
                "read_evidence",
                "create_submission",
                "update_submission",
                "validate_submission",
                "submit_submission",
                "create_import_batch",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "create_connection_request",
                "decide_connection_request",
                "read_connection_request",
                "create_consent",
                "revoke_consent",
                "create_evidence_upload",
                "create_evidence_version",
                "grant_evidence_access",
                "revoke_evidence_access",
                "update_evidence_retention",
                "read_invoice",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
            }
        ),
        "buyer_admin": frozenset(
            {
                "read_graph",
                "read_business",
                "read_connection_request",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "create_connection_request",
                "create_consent",
                "read_invoice",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
            }
        ),
        "supplier_admin": frozenset(
            {
                "read_business",
                "read_financials",
                "read_evidence",
                "read_connection_request",
                "create_submission",
                "update_submission",
                "validate_submission",
                "submit_submission",
                "create_import_batch",
                "read_supply_map_registration",
                "create_supply_map_registration",
                "create_consent",
                "decide_connection_request",
                "revoke_consent",
                "create_evidence_upload",
                "create_evidence_version",
                "grant_evidence_access",
                "revoke_evidence_access",
                "update_evidence_retention",
                "read_invoice",
                "read_risk_run",
                "read_match_run",
                "read_scenario_run",
            }
        ),
        "reviewer": frozenset({"read_business", "read_financials", "read_evidence", "review_submission", "read_supply_map_registration", "review_supply_map_registration", "read_connection_request", "decide_connection_request", "read_risk_run", "read_match_run", "read_scenario_run"}),
        "network_analyst": frozenset({"read_graph", "read_supply_map_registration", "read_risk_run", "read_match_run", "read_scenario_run"}),
        "lender": frozenset({"read_financials", "read_evidence", "read_supply_map_registration", "create_supply_map_registration", "read_invoice", "register_invoice_claim", "transition_invoice_claim", "read_risk_run", "read_scenario_run"}),
        "evidence_scanner": frozenset({"read_evidence", "record_malware_scan_result"}),
    }

    @classmethod
    def decide(
        cls,
        action: str,
        context: RequestContext,
        *,
        resource_type: str = "organization",
        resource_id: str | None = None,
        resource_organization_id: str | None = None,
        data_classification: str | None = None,
        external_access_allowed: bool = False,
    ) -> PolicyDecision:
        if context.tenant_id != "tenant-demo" and context.app_mode == "demo":
            return cls._deny(action, "Demo mode only trusts tenant-demo contexts.", resource_type, resource_id, data_classification)
        if context.has_role("demo_admin", "system_admin") or "policy:override" in context.scopes:
            return cls._allow(action, "Administrative override.", resource_type, resource_id, data_classification)
        if action == "unmask_graph" and not context.has_scope(SENSITIVE_GRAPH_SCOPE):
            return cls._deny(action, "Unmasked graph requires commercial_graph:read scope.", resource_type, resource_id, data_classification)
        if action == "unmask_graph" and context.has_scope(SENSITIVE_GRAPH_SCOPE) and context.has_role("network_analyst", "lender", "reviewer", "demo_operator"):
            return cls._allow(action, "Sensitive graph scope and role accepted.", resource_type, resource_id, data_classification)
        allowed = any("*" in cls.ROLE_ACTIONS.get(role, frozenset()) or action in cls.ROLE_ACTIONS.get(role, frozenset()) for role in context.roles)
        if not allowed:
            return cls._deny(action, f"Actor roles {sorted(context.roles)} cannot perform {action}.", resource_type, resource_id, data_classification)
        if (
            resource_organization_id
            and resource_organization_id not in context.organization_ids
            and not context.is_demo_actor()
            and not external_access_allowed
        ):
            return cls._deny(action, "Actor is not a member of the resource organization.", resource_type, resource_id, data_classification)
        return cls._allow(action, "Role, organization and purpose policy passed.", resource_type, resource_id, data_classification)

    @classmethod
    def require(cls, action: str, context: RequestContext, **kwargs: Any) -> PolicyDecision:
        decision = cls.decide(action, context, **kwargs)
        if decision.effect != "allow":
            raise AccessDeniedError("POLICY_DENIED", decision.reason, status_code=403)
        return decision

    @classmethod
    def capability_matrix(
        cls,
        context: RequestContext,
        *,
        resource_organization_id: str | None = None,
    ) -> dict[str, Any]:
        organization_id = resource_organization_id or context.organization_id or None
        capabilities: dict[str, bool] = {}
        decisions: dict[str, str] = {}
        for capability, action in cls.CAPABILITY_ACTIONS.items():
            decision = cls.decide(
                action,
                context,
                resource_type="actor_capability",
                resource_id=organization_id,
                resource_organization_id=organization_id,
                data_classification="restricted_commercial" if action == "unmask_graph" else "confidential",
            )
            capabilities[capability] = decision.effect == "allow"
            decisions[capability] = decision.reason
        allowed_actions = [
            action
            for capability, action in cls.CAPABILITY_ACTIONS.items()
            if capabilities[capability]
        ]
        return {
            **capabilities,
            "allowed_actions": allowed_actions,
            "decision_reasons": decisions,
        }

    @classmethod
    def workspace_access(
        cls,
        context: RequestContext,
        *,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        caps = capabilities or cls.capability_matrix(context)
        views = {
            "overview": any(
                caps.get(name)
                for name in (
                    "can_read_graph",
                    "can_create_submission",
                    "can_create_connection_request",
                    "can_register_invoice_claim",
                    "can_read_audit",
                )
            ),
            "map": bool(caps.get("can_read_graph")),
            "companies": bool(caps.get("can_read_business") or caps.get("can_read_evidence")),
            "intake": any(
                caps.get(name)
                for name in (
                    "can_create_submission",
                    "can_update_submission",
                    "can_validate_submission",
                    "can_submit_submission",
                    "can_review_submission",
                    "can_create_import_batch",
                )
            ),
            "onboarding": bool(
                caps.get("can_read_supply_map_registration")
                or caps.get("can_create_supply_map_registration")
                or caps.get("can_review_supply_map_registration")
            ),
            "risk": bool(caps.get("can_read_risk_run")),
            "matching": bool(caps.get("can_read_match_run") or caps.get("can_create_connection_request")),
            "finance": bool(caps.get("can_read_financials") or caps.get("can_register_invoice_claim")),
            "invoice": bool(
                caps.get("can_read_invoice")
                or caps.get("can_register_invoice_claim")
                or caps.get("can_transition_invoice_claim")
            ),
            "audit": bool(caps.get("can_read_audit")),
        }
        ordered = ["overview", "map", "companies", "intake", "onboarding", "risk", "matching", "finance", "invoice", "audit"]
        allowed_views = [view for view in ordered if views[view]]
        task_defaults = [
            ("intake", any(caps.get(name) for name in ("can_review_submission", "can_create_submission", "can_update_submission", "can_validate_submission", "can_submit_submission", "can_create_import_batch"))),
            ("finance", bool(caps.get("can_read_financials") or caps.get("can_register_invoice_claim"))),
            ("invoice", bool(caps.get("can_register_invoice_claim") or caps.get("can_transition_invoice_claim"))),
            ("overview", bool(caps.get("can_read_graph") or caps.get("can_create_connection_request") or caps.get("can_read_audit"))),
            ("onboarding", bool(caps.get("can_review_supply_map_registration") or caps.get("can_create_supply_map_registration") or caps.get("can_read_supply_map_registration"))),
        ]
        default_view = next((view for view, enabled in task_defaults if enabled and views.get(view)), allowed_views[0] if allowed_views else None)
        return {
            "views": views,
            "allowed_views": allowed_views,
            "default_view": default_view,
        }

    @classmethod
    def deny_decision(
        cls,
        action: str,
        reason: str,
        *,
        resource_type: str = "unknown",
        resource_id: str | None = None,
        data_classification: str | None = None,
    ) -> PolicyDecision:
        return cls._deny(action, reason, resource_type, resource_id, data_classification)

    @staticmethod
    def _allow(action: str, reason: str, resource_type: str, resource_id: str | None, data_classification: str | None) -> PolicyDecision:
        return PolicyDecision(f"POL-{uuid4().hex[:12].upper()}", action, "allow", reason, resource_type, resource_id, data_classification)

    @staticmethod
    def _deny(action: str, reason: str, resource_type: str, resource_id: str | None, data_classification: str | None) -> PolicyDecision:
        return PolicyDecision(f"POL-{uuid4().hex[:12].upper()}", action, "deny", reason, resource_type, resource_id, data_classification)


def graph_mask_for_request(masked: bool, context: RequestContext | None = None) -> bool:
    active_context = context or RequestContext.demo()
    if masked:
        PolicyService.require("read_graph", active_context, resource_type="commercial_graph", data_classification="confidential")
        return True
    PolicyService.require("unmask_graph", active_context, resource_type="commercial_graph", data_classification="restricted_commercial")
    return False
