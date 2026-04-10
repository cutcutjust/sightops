"""Custom exceptions for XAgent."""


class XAgentError(Exception):
    """Base exception."""


class BrowserError(XAgentError):
    """Browser / Playwright error."""


class VisionError(XAgentError):
    """LLM vision or action planning error."""


class ActionFailed(XAgentError):
    """An action was executed but produced an unexpected result."""


class ExtractionError(XAgentError):
    """Failed to extract content from a page."""


class PublishError(XAgentError):
    """Publishing failed or was rejected."""


class NotionError(XAgentError):
    """Notion API error."""


class HumanReviewRequired(XAgentError):
    """Workflow paused — human must review before continuing."""
