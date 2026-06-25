"""Unit tests for AuthService (non-DB parts)."""
import pytest
from datetime import datetime, timedelta
from app.services.auth_service import AuthService, AuthError


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_string(self):
        hashed = AuthService.hash_password("test123")
        assert isinstance(hashed, str)
        assert len(hashed) > 20

    def test_hash_password_different_each_time(self):
        """bcrypt generates unique salts."""
        h1 = AuthService.hash_password("test123")
        h2 = AuthService.hash_password("test123")
        assert h1 != h2

    def test_verify_password_correct(self):
        hashed = AuthService.hash_password("mypassword")
        assert AuthService.verify_password("mypassword", hashed) is True

    def test_verify_password_wrong(self):
        hashed = AuthService.hash_password("mypassword")
        assert AuthService.verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        hashed = AuthService.hash_password("test")
        assert AuthService.verify_password("", hashed) is False


class TestJWT:
    """Tests for JWT token creation and validation."""

    def test_create_token_returns_string(self):
        token = AuthService.create_token(user_id=1)
        assert isinstance(token, str)
        assert len(token) > 50

    def test_decode_token_valid(self):
        token = AuthService.create_token(user_id=42, is_admin=True)
        payload = AuthService.decode_token(token)
        assert payload["sub"] == "42"
        assert payload["is_admin"] is True

    def test_decode_token_invalid(self):
        with pytest.raises(AuthError, match="Invalid token"):
            AuthService.decode_token("not.a.valid.token")

    def test_decode_token_expired(self):
        """Expired tokens should raise AuthError."""
        import jwt
        from app.config import settings

        payload = {
            "sub": "1",
            "is_admin": False,
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(AuthError, match="Token expired"):
            AuthService.decode_token(token)

    def test_token_contains_user_id(self):
        token = AuthService.create_token(user_id=99)
        payload = AuthService.decode_token(token)
        assert int(payload["sub"]) == 99

    def test_token_default_not_admin(self):
        token = AuthService.create_token(user_id=1)
        payload = AuthService.decode_token(token)
        assert payload["is_admin"] is False
