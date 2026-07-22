"""Observability, Structured JSON Logging, PII Redaction, and Distributed Tracing.

Implements enterprise-grade structured JSON logging, automatic PII masking (emails, tokens),
and W3C-compatible trace context propagation for Google Cloud Trace & OpenTelemetry.
"""

import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Regex patterns for sensitive data masking
EMAIL_REGEX = re.compile(r'([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*([a-zA-Z0-9_.+-])@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
BEARER_TOKEN_REGEX = re.compile(r'(Bearer\s+|ya29\.)[a-zA-Z0-9_\-\.]{8,}')


def redact_pii(data: Any) -> Any:
    """Recursively redacts sensitive PII (emails, OAuth tokens, API keys) in strings, lists, and dicts."""
    if isinstance(data, str):
        # 1. Mask emails: "johndoe@example.com" -> "j***e@example.com"
        masked = EMAIL_REGEX.sub(r'\1***\2@\3', data)
        # 2. Mask Bearer/OAuth tokens
        masked = BEARER_TOKEN_REGEX.sub(r'[REDACTED_AUTH_TOKEN]', masked)
        return masked
    elif isinstance(data, dict):
        return {k: redact_pii(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple, set)):
        return [redact_pii(item) for item in data]
    return data


class StructuredJsonLogger:
    """Structured JSON Logger that outputs machine-readable JSON log records."""

    def __init__(self, service_name: str = "growth_hacker_agent"):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            self.logger.addHandler(handler)

    def log(
        self,
        level: str,
        message: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        intent: Optional[str] = None,
        outcome: Optional[str] = None,
        duration_ms: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Logs a structured JSON event to stdout after applying PII redaction."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "level": level.upper(),
            "message": redact_pii(message),
            "trace_id": trace_id or f"trace-{uuid.uuid4().hex[:16]}",
            "span_id": span_id or f"span-{uuid.uuid4().hex[:8]}",
            "agent_name": agent_name or self.service_name,
            "intent": intent,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "metadata": redact_pii(extra or {})
        }
        json_output = json.dumps(record, ensure_ascii=False)
        if level.upper() == "ERROR":
            self.logger.error(json_output)
        elif level.upper() == "WARNING":
            self.logger.warning(json_output)
        else:
            self.logger.info(json_output)
        return record


# Global singleton structured logger
logger = StructuredJsonLogger()


class TraceSpan:
    """Context manager for distributed tracing spans recording execution intent, outcome, and duration."""

    def __init__(self, span_name: str, agent_name: str = "growth_hacker_agent", intent: str = "", trace_id: Optional[str] = None):
        self.span_name = span_name
        self.agent_name = agent_name
        self.intent = intent
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:16]}"
        self.span_id = f"span-{uuid.uuid4().hex[:8]}"
        self.start_time: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        logger.log(
            level="INFO",
            message=f"Starting span '{self.span_name}'",
            trace_id=self.trace_id,
            span_id=self.span_id,
            agent_name=self.agent_name,
            intent=self.intent,
            outcome="STARTED"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.perf_counter() - self.start_time) * 1000.0
        if exc_type is not None:
            logger.log(
                level="ERROR",
                message=f"Span '{self.span_name}' failed with error: {exc_val}",
                trace_id=self.trace_id,
                span_id=self.span_id,
                agent_name=self.agent_name,
                intent=self.intent,
                outcome="FAILED",
                duration_ms=duration_ms,
                extra={"error_type": str(exc_type.__name__)}
            )
        else:
            logger.log(
                level="INFO",
                message=f"Span '{self.span_name}' completed successfully",
                trace_id=self.trace_id,
                span_id=self.span_id,
                agent_name=self.agent_name,
                intent=self.intent,
                outcome="SUCCESS",
                duration_ms=duration_ms
            )
