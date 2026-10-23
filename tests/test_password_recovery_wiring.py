"""Regression tests for the password-recovery wiring in the auth routes.

Guards against the bug where forgot_password called
``auth_service.send_recovery_code(...)`` — but send_recovery_code is a
module-level function, not an AuthService method — causing an AttributeError
and a 500 for accounts that actually have Telegram linked.
"""
import inspect

from app.services import auth_service as auth_service_module
from app.services.auth_service import AuthService, send_recovery_code, build_recovery_message


def test_send_recovery_code_is_module_function_not_method():
    # It must exist at module scope...
    assert callable(send_recovery_code)
    # ...and must NOT be an attribute of the AuthService instance/class.
    assert not hasattr(AuthService, "send_recovery_code")
    assert not hasattr(auth_service_module.auth_service, "send_recovery_code")


def test_auth_route_imports_send_recovery_code_from_module():
    # The route module must import the module-level function (the fix), so the
    # forgot-password handler can call it without the auth_service prefix.
    from app.routes import auth as auth_route
    assert auth_route.send_recovery_code is send_recovery_code


def test_forgot_password_does_not_reference_auth_service_send():
    # The handler source must not call auth_service.send_recovery_code (the bug).
    from app.routes import auth as auth_route
    src = inspect.getsource(auth_route.forgot_password)
    assert "auth_service.send_recovery_code" not in src
    assert "send_recovery_code(" in src


def test_authservice_has_the_real_methods():
    # These ARE methods on AuthService (contrast with send_recovery_code).
    assert hasattr(AuthService, "create_password_reset_token")
    assert hasattr(AuthService, "is_rate_limited")
    assert hasattr(AuthService, "validate_and_consume_reset")


def test_build_recovery_message_contains_code_and_minutes():
    msg = build_recovery_message("123456")
    assert "123456" in msg
    assert "15" in msg  # validity minutes
