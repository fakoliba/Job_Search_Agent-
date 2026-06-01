from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules import auth


class AuthTests(unittest.TestCase):
    def test_create_and_authenticate_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_file = auth.USERS_FILE
            auth.USERS_FILE = Path(tmpdir) / "users.json"
            try:
                created = auth.create_user(
                    first_name="Cherif",
                    last_name="M",
                    email="Cherif@example.com",
                    password="password123",
                )
                authenticated = auth.authenticate_user("cherif@example.com", "password123")
                rejected = auth.authenticate_user("cherif@example.com", "wrong-password")

                self.assertEqual(created["username"], "cherif@example.com")
                self.assertEqual(created["email"], "cherif@example.com")
                self.assertEqual(created["first_name"], "Cherif")
                self.assertEqual(authenticated["username"], "cherif@example.com")
                self.assertIsNone(rejected)
            finally:
                auth.USERS_FILE = original_file

    def test_update_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_file = auth.USERS_FILE
            auth.USERS_FILE = Path(tmpdir) / "users.json"
            try:
                user = auth.create_user(
                    first_name="Cherif",
                    last_name="M",
                    email="cherif@example.com",
                    password="password123",
                )
                updated = auth.update_user_profile(
                    user["username"],
                    target_role_family="AI Engineer",
                    target_seniority="Staff",
                    preferred_locations="Remote, San Francisco",
                    needs_sponsorship=False,
                    years_experience=12,
                )

                self.assertEqual(updated["profile"]["target_role_family"], "AI Engineer")
                self.assertEqual(updated["profile"]["target_seniority"], "Staff")
                self.assertEqual(updated["profile"]["years_experience"], 12)
            finally:
                auth.USERS_FILE = original_file

    def test_legacy_username_authentication_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_file = auth.USERS_FILE
            auth.USERS_FILE = Path(tmpdir) / "users.json"
            try:
                salt, password_hash = auth.hash_password("password123")
                auth.save_users(
                    [
                        {
                            "id": "legacy",
                            "username": "cherif",
                            "salt": salt,
                            "password_hash": password_hash,
                        }
                    ]
                )

                authenticated = auth.authenticate_user("cherif", "password123")

                self.assertEqual(authenticated["username"], "cherif")
                self.assertEqual(authenticated["email"], "cherif")
            finally:
                auth.USERS_FILE = original_file


if __name__ == "__main__":
    unittest.main()
