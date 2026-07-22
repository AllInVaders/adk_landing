import unittest
from growth_hacker_agent.schemas import (
    WriteLandingPageInput,
    WriteLandingPageResult,
    DeployLandingPageInput,
    DeployLandingPageResult,
    FetchWaitlistEmailsResult
)


class TestSchemas(unittest.TestCase):
    """Verifies strict Pydantic v2 input and output validation contracts."""

    def test_write_landing_page_input_valid(self):
        data = {
            "project_name": "SmartBrew Kettle",
            "html_content": "<!DOCTYPE html><html><body><h1>Title</h1></body></html>",
            "css_content": "body { background: #000; }",
            "js_content": "console.log('ready');"
        }
        model = WriteLandingPageInput(**data)
        self.assertEqual(model.project_name, "smartbrew kettle")

    def test_write_landing_page_input_invalid_empty(self):
        with self.assertRaises(Exception):
            WriteLandingPageInput(
                project_name="",
                html_content="<h1>Short</h1>",
                css_content="body{}",
                js_content="test"
            )

    def test_deploy_landing_page_result_schema(self):
        result = DeployLandingPageResult(
            status="success",
            service_name="lp-smartbrew",
            live_url="https://lp-smartbrew-xyz.run.app",
            region="us-central1",
            project_id="genai-demos"
        )
        dump = result.model_dump()
        self.assertEqual(dump["status"], "success")
        self.assertEqual(dump["service_name"], "lp-smartbrew")

    def test_fetch_waitlist_emails_result(self):
        result = FetchWaitlistEmailsResult(
            status="success",
            service_name="lp-smartbrew",
            leads_count=2,
            emails=["a***z@test.com", "b***y@test.com"]
        )
        self.assertEqual(result.leads_count, 2)


if __name__ == "__main__":
    unittest.main()
