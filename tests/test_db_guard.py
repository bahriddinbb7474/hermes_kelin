"""Unit tests for tests.db_guard (Блок 6Ж). No database connection is made."""
import os
import unittest

from tests.db_guard import (
    DestructiveTestTargetError,
    validate_destructive_test_target,
)

# Вымышленные URL/пароли — не реальные credentials.
_FAKE = "postgresql://test_user:fake_secret@127.0.0.1:5432/{db}"


class GuardTests(unittest.TestCase):

    # A. Нет DATABASE_URL -> REFUSED
    def test_a_no_url(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target("", "test", False)
        self.assertEqual(ctx.exception.reason, "missing_url")

    # B. APP_ENV отсутствует -> REFUSED
    def test_b_no_app_env(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(_FAKE.format(db="hermes_test"), None, False)
        self.assertEqual(ctx.exception.reason, "app_env_not_test")

    # C. APP_ENV=prod, БД hermes_test -> REFUSED
    def test_c_prod_env(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(_FAKE.format(db="hermes_test"), "prod", False)
        self.assertEqual(ctx.exception.reason, "app_env_not_test")

    # D. APP_ENV=test, localhost, БД hermes -> REFUSED
    def test_d_prod_db_localhost(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(_FAKE.format(db="hermes"), "test", False)
        self.assertEqual(ctx.exception.reason, "prod_db_name")

    # E. APP_ENV=test, localhost, БД hermes, ALLOW_DESTRUCTIVE_TESTS=1 -> REFUSED
    def test_e_prod_db_override_cannot_bypass(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(_FAKE.format(db="hermes"), "test", True)
        self.assertEqual(ctx.exception.reason, "prod_db_name")

    # F. APP_ENV=test, 127.0.0.1, БД hermes_test -> PASS
    def test_f_local_test_db(self):
        res = validate_destructive_test_target(_FAKE.format(db="hermes_test"), "test", False)
        self.assertEqual(res.db_name, "hermes_test")
        self.assertTrue(res.local)

    # G. APP_ENV=test, localhost, БД project_test -> PASS
    def test_g_local_other_test_db(self):
        url = "postgresql://u:p@localhost:5432/project_test"
        res = validate_destructive_test_target(url, "test", False)
        self.assertEqual(res.db_name, "project_test")
        self.assertTrue(res.local)

    # H. APP_ENV=test, удалённый host, БД hermes_test, без override -> REFUSED
    def test_h_remote_without_override(self):
        url = "postgresql://u:p@10.0.0.5:5432/hermes_test"
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(url, "test", False)
        self.assertEqual(ctx.exception.reason, "remote_requires_override")

    # I. APP_ENV=test, удалённый host, БД hermes_test, override -> PASS
    def test_i_remote_with_override(self):
        url = "postgresql://u:p@10.0.0.5:5432/hermes_test"
        res = validate_destructive_test_target(url, "test", True)
        self.assertEqual(res.db_name, "hermes_test")
        self.assertFalse(res.local)

    # J. Имя 'hermes_test_backup' -> REFUSED (только точное окончание '_test')
    def test_j_lookalike_suffix_refused(self):
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(_FAKE.format(db="hermes_test_backup"), "test", False)
        self.assertEqual(ctx.exception.reason, "bad_db_suffix")

    # K. Ошибка не содержит пароль из тестового URL
    def test_k_error_message_no_secret(self):
        url = "postgresql://test_user:super_secret_pw@127.0.0.1:5432/hermes"
        with self.assertRaises(DestructiveTestTargetError) as ctx:
            validate_destructive_test_target(url, "test", False)
        msg = str(ctx.exception)
        self.assertNotIn("super_secret_pw", msg)
        self.assertNotIn("test_user", msg)
        self.assertNotIn(url, msg)


if __name__ == "__main__":
    unittest.main()
