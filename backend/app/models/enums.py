from enum import StrEnum


class FlowStatus(StrEnum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ACTIVE = "active"
    ARCHIVED = "archived"


class StepAction(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    PRESS = "press"


class VersionSource(StrEnum):
    RECORDING = "recording"
    SIMILARITY = "similarity"
    LLM = "llm"
    HUMAN = "human"


class VariableSource(StrEnum):
    COLUMN = "column"
    PREVIOUS_MONTH = "previous_month"
    TODAY = "today"


class VariableStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"


class RunTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"


class ItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    REPAIRED = "repaired"
    WAITING_HUMAN = "waiting_human"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    WAITING_HUMAN = "waiting_human"


class LogLevel(StrEnum):
    INFO = "info"
    OK = "ok"
    FAILURE = "failure"
    SEARCH = "search"


class ArtifactKind(StrEnum):
    FILE = "file"
    SCREENSHOT = "screenshot"


class HelpKind(StrEnum):
    CONFIRM = "confirm"
    CHOOSE = "choose"
    CAPTCHA = "captcha"
    UNCERTAIN = "uncertain"


class HelpStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    EXPIRED = "expired"
