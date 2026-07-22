import unittest
from growth_hacker_agent.observability import redact_pii, StructuredJsonLogger, TraceSpan


class TestObservability(unittest.TestCase):
    """Verifies structured JSON logging, distributed tracing, and PII masking."""

    def test_pii_redaction_email(self):
        raw_text = "Waitlist signup from andres.villa@google.com received!"
        redacted = redact_pii(raw_text)
        self.assertNotIn("andres.villa@google.com", redacted)
        self.assertIn("@google.com", redacted)

    def test_pii_redaction_token(self):
        raw_dict = {"auth": "Bearer ya29.a0AfH6SMDk9912388123abcdef"}
        redacted = redact_pii(raw_dict)
        self.assertEqual(redacted["auth"], "[REDACTED_AUTH_TOKEN]")

    def test_structured_logger_record(self):
        logger = StructuredJsonLogger(service_name="test_agent")
        record = logger.log(
            level="INFO",
            message="Test structured event",
            intent="TEST_INTENT",
            outcome="SUCCESS"
        )
        self.assertEqual(record["service"], "test_agent")
        self.assertEqual(record["intent"], "TEST_INTENT")
        self.assertEqual(record["outcome"], "SUCCESS")

    def test_trace_span(self):
        with TraceSpan(span_name="test_span", agent_name="test_agent", intent="SPAN_TEST") as span:
            self.assertTrue(span.trace_id.startswith("trace-"))
            self.assertTrue(span.span_id.startswith("span-"))


if __name__ == "__main__":
    unittest.main()
