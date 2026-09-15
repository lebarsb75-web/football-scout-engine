import unittest

from fastapi.testclient import TestClient

from api.app import app


class WebApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_local_web_origin_can_preflight_submission(self):
        response = self.client.options(
            "/analysis/submit",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-idempotency-key,x-cost-approval-secret",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:4173",
        )

    def test_unknown_origin_is_not_allowed(self):
        response = self.client.options(
            "/analysis/submit",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
