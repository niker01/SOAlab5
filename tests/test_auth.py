import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

import auth


class FakeJwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        jwt.get_unverified_header(token)
        return SimpleNamespace(key=self.key)


class AuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        cls.other_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

    def _token(self, scopes, private_key=None):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": "https://identity.example/realms/soa",
                "aud": "todo-api",
                "sub": "user-123",
                "iat": now,
                "exp": now + 60,
                "scope": " ".join(scopes),
            },
            private_key or self.private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

    @patch.multiple(
        auth,
        KEYCLOAK_ISSUER="https://identity.example/realms/soa",
        API_AUDIENCE="todo-api",
    )
    @patch("auth._jwks_client")
    def test_valid_jwt_with_required_scope_is_accepted(self, jwks_client):
        jwks_client.return_value = FakeJwksClient(self.private_key.public_key())
        token = self._token(["tasks:read"])

        claims = auth.verify_authorization(
            f"Bearer {token}",
            ["tasks:read"],
        )

        self.assertEqual(claims["sub"], "user-123")

    @patch.multiple(
        auth,
        KEYCLOAK_ISSUER="https://identity.example/realms/soa",
        API_AUDIENCE="todo-api",
    )
    @patch("auth._jwks_client")
    def test_valid_jwt_without_required_scope_is_forbidden(self, jwks_client):
        jwks_client.return_value = FakeJwksClient(self.private_key.public_key())
        token = self._token(["tasks:read"])

        with self.assertRaises(HTTPException) as raised:
            auth.verify_authorization(f"Bearer {token}", ["tasks:write"])

        self.assertEqual(raised.exception.status_code, 403)

    @patch.multiple(
        auth,
        KEYCLOAK_ISSUER="https://identity.example/realms/soa",
        API_AUDIENCE="todo-api",
    )
    @patch("auth._jwks_client")
    def test_jwt_with_invalid_signature_is_rejected(self, jwks_client):
        jwks_client.return_value = FakeJwksClient(self.private_key.public_key())
        token = self._token(["tasks:read"], self.other_private_key)

        with self.assertRaises(HTTPException) as raised:
            auth.verify_authorization(f"Bearer {token}", ["tasks:read"])

        self.assertEqual(raised.exception.status_code, 401)

    @patch("auth._jwks_client")
    def test_malformed_jwt_is_rejected_as_unauthorized(self, jwks_client):
        jwks_client.return_value = FakeJwksClient(self.private_key.public_key())

        with self.assertRaises(HTTPException) as raised:
            auth.verify_authorization("Bearer invalid-token", ["tasks:read"])

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
