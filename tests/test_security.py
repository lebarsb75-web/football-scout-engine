import os
import unittest
from unittest.mock import patch

from api.security import approval_secret_matches, validate_video_url_for_submission


class VideoUrlSecurityTests(unittest.TestCase):
    def test_paid_submission_requires_allowlist(self):
        with patch.dict(os.environ, {"VIDEO_HOST_ALLOWLIST": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "VIDEO_HOST_ALLOWLIST"):
                validate_video_url_for_submission("https://videos.example.com/match.mp4")

    def test_allowed_host_and_subdomain_pass(self):
        with patch.dict(
            os.environ,
            {"VIDEO_HOST_ALLOWLIST": "storage.example.com"},
            clear=False,
        ):
            validate_video_url_for_submission("https://storage.example.com/match.mp4")
            validate_video_url_for_submission("https://signed.storage.example.com/match.mp4")

    def test_unapproved_host_is_rejected(self):
        with patch.dict(
            os.environ,
            {"VIDEO_HOST_ALLOWLIST": "storage.example.com"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "not in VIDEO_HOST_ALLOWLIST"):
                validate_video_url_for_submission("https://example.net/match.mp4")

    def test_local_and_private_hosts_are_rejected(self):
        with patch.dict(
            os.environ,
            {"VIDEO_HOST_ALLOWLIST": "localhost,127.0.0.1,10.0.0.1"},
            clear=False,
        ):
            for url in (
                "http://localhost/match.mp4",
                "http://127.0.0.1/match.mp4",
                "http://10.0.0.1/match.mp4",
            ):
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        validate_video_url_for_submission(url)

    def test_url_credentials_are_rejected(self):
        with patch.dict(
            os.environ,
            {"VIDEO_HOST_ALLOWLIST": "storage.example.com"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "Credentials"):
                validate_video_url_for_submission(
                    "https://user:pass@storage.example.com/match.mp4"
                )


class CostApprovalSecretTests(unittest.TestCase):
    def test_secret_matching_is_fail_closed(self):
        with patch.dict(os.environ, {"COST_APPROVAL_SECRET": ""}, clear=False):
            self.assertFalse(approval_secret_matches(None))
            self.assertFalse(approval_secret_matches("anything"))

    def test_secret_must_match_exactly(self):
        with patch.dict(
            os.environ,
            {"COST_APPROVAL_SECRET": "approved-on-server"},
            clear=False,
        ):
            self.assertTrue(approval_secret_matches("approved-on-server"))
            self.assertFalse(approval_secret_matches("wrong"))


if __name__ == "__main__":
    unittest.main()
