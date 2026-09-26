import unittest
from unittest.mock import patch
from redactor import redact, safe_record


class RedactionTest(unittest.TestCase):
    def test_urls_and_error_context(self):
        marker = "F10_PRIVATE_MARKER"
        for path in (
            f"/users/log-in/{marker}", f"/book/restore/{marker}",
            f"/orders/K-000001/{marker}/invoice",
            f"/orders/K-000001/{marker}/rate/5",
            f"/print-files/id/interior?t={marker}",
            f"/checkout/return?token={marker}",
            f"/users/%6Cog-in/{marker}",
            f"//book//restore/{marker}",
            f"/book/unused/../restore/{marker}",
            f"/checkout/return?t=prefix%20{marker}",
        ):
            with self.subTest(path=path):
                message = (
                    f'connect() failed (111: Connection refused), request: "GET {path} HTTP/1.1", '
                    f'upstream: "http://172.18.0.5:4000{path}", '
                    f'referrer: "https://getkinfolio.com/book/restore/{marker}"'
                )
                cleaned = redact(message)
                self.assertNotIn(marker, cleaned)
                self.assertIn("connect() failed (111: Connection refused)", cleaned)
                self.assertIn("[FILTERED]", cleaned)

    def test_normal_diagnostics(self):
        message = 'getkinfolio_access: {"path":"/book/view","status":200,"duration":"0.012"}'
        self.assertEqual(redact(message), message)

    def test_failure_withholds_input_and_error_text(self):
        with patch("redactor.redact", side_effect=ValueError("F10_PRIVATE_MARKER")):
            output = safe_record(b"F10_PRIVATE_MARKER")
        self.assertNotIn("F10_PRIVATE_MARKER", output)
        self.assertIn("redaction failed", output)


if __name__ == "__main__":
    unittest.main()
