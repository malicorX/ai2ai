"""
All data models: dataclasses for internal state, Pydantic models for API requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --- Type aliases ---
AuthorType = Literal["agent", "human", "system"]
AudienceType = Literal["public", "humans", "agents"]
PostStatus = Literal["open", "closed", "moderated"]
JobStatus = Literal["open", "claimed", "submitted", "approved", "rejected", "cancelled"]
JobEventType = Literal["create", "claim", "submit", "verify", "review", "update", "cancel", "unclaim"]
EconomyEntryType = Literal["genesis", "transfer", "award", "spend", "paypal_payment"]
EventStatus = Literal["scheduled", "cancelled", "completed"]
RsvpStatus = Literal["yes", "no", "maybe"]
EventEventType = Literal["create", "invite", "rsvp", "cancel"]
TraceKind = Literal["thought", "action", "error", "status"]
MemoryKind = Literal["note", "event", "reflection", "plan", "summary"]


# --- Internal state dataclasses ---

@dataclass
class AgentState:
    agent_id: str
    display_name: str
    x: int = 0
    y: int = 0
    last_seen_at: float = 0.0


@dataclass
class AuditEntry:
    audit_id: str
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float
    client: str
    content_type: str
    body_preview: str
    body_json: Optional[dict]
    created_at: float


@dataclass
class ChatMessage:
    msg_id: str
    sender_type: AuthorType
    sender_id: str
    sender_name: str
    text: str
    created_at: float


@dataclass
class BoardPost:
    post_id: str
    author_type: AuthorType
    author_id: str
    audience: str
    title: str
    body: str
    tags: List[str]
    status: PostStatus
    created_at: float
    updated_at: float


@dataclass
class BoardReply:
    reply_id: str
    post_id: str
    author_type: AuthorType
    author_id: str
    body: str
    created_at: float


@dataclass
class Opportunity:
    opp_id: str
    fingerprint: str
    title: str
    platform: str
    demand_signal: str
    estimated_price_usd: str
    why_fit: str
    first_action: str
    source_url: str
    source_quote: str
    source_domain: str
    status: str
    tags: list[str]
    notes: str
    created_at: float
    last_seen_at: float
    run_ids: list[str]
    job_ids: list[str]
    client_response: str
    outcome: str
    success_score: float
    actual_revenue_usd: float
    estimated_value_score: float


@dataclass
class EconomyEntry:
    entry_id: str
    entry_type: EconomyEntryType
    amount: float
    from_id: str
    to_id: str
    memo: str
    created_at: float


@dataclass
class Job:
    job_id: str
    title: str
    body: str
    reward: float
    status: JobStatus
    created_by: str
    created_at: float
    claimed_by: str
    claimed_at: float
    submitted_by: str
    submitted_at: float
    submission: str
    reviewed_by: str
    reviewed_at: float
    review_note: str
    auto_verify_ok: Optional[bool] = None
    auto_verify_name: str = ""
    auto_verify_note: str = ""
    auto_verify_artifacts: dict = field(default_factory=dict)
    auto_verified_at: float = 0.0
    fingerprint: str = ""
    ratings: dict = field(default_factory=dict)
    reward_mode: str = "manual"
    reward_calc: dict = field(default_factory=dict)
    source: str = "unknown"
    parent_job_id: str = ""


@dataclass
class JobEvent:
    event_id: str
    event_type: JobEventType
    job_id: str
    data: dict
    created_at: float


@dataclass
class VillageEvent:
    event_id: str
    title: str
    description: str
    location_id: str
    start_day: int
    start_minute: int
    duration_min: int
    status: EventStatus
    created_by: str
    created_at: float
    invites: List[dict]
    rsvps: Dict[str, str]


@dataclass
class EventLogEntry:
    log_id: str
    event_type: EventEventType
    event_id: str
    data: dict
    created_at: float


@dataclass
class TraceEvent:
    event_id: str
    agent_id: str
    agent_name: str
    kind: TraceKind
    summary: str
    data: dict
    created_at: float


@dataclass
class MemoryEntry:
    memory_id: str
    agent_id: str
    kind: MemoryKind
    text: str
    tags: List[str]
    importance: float
    created_at: float


@dataclass
class AutoVerifyOutcome:
    matched: bool
    ok: bool
    note: str
    verifier: str
    artifacts: dict


# --- Pydantic request models ---

class MoveRequest(BaseModel):
    dx: Optional[int] = None
    dy: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


class WorldActionRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    action: str
    params: dict = Field(default_factory=dict)


class TokenRequest(BaseModel):
    agent_name: str
    purpose: str = ""
    contact: str = ""


class RegisterAgentRequest(BaseModel):
    display_name: str = ""
    agent_id: str = ""
    registration_secret: str = ""


class TokenIssueRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    notes: str = ""


class MoltWorldWebhookRequest(BaseModel):
    agent_id: str
    url: str
    secret: Optional[str] = None


class UpsertAgentRequest(BaseModel):
    agent_id: str
    display_name: str = Field(default_factory=str)


class WorldSnapshot(BaseModel):
    world_size: int
    tick: int
    day: int
    minute_of_day: int
    landmarks: List[dict]
    agents: List[dict]
    recent_chat: List[dict] = []
    rules: str = ""
    rules_reminder: str = "Check the 'rules' field (or GET /rules) to see what gives or costs ai$. You should read the rules."


class CreatePostRequest(BaseModel):
    title: str
    body: str
    audience: str = "humans"
    tags: List[str] = Field(default_factory=list)
    author_type: AuthorType = "agent"
    author_id: str = ""


class CreateReplyRequest(BaseModel):
    body: str
    author_type: AuthorType = "human"
    author_id: str = "human"


class ChatSendRequest(BaseModel):
    sender_type: AuthorType = "agent"
    sender_id: str
    sender_name: str
    text: str


class ChatBroadcastRequest(BaseModel):
    sender_id: str
    sender_name: str
    text: str


class TransferRequest(BaseModel):
    from_id: str
    to_id: str
    amount: float
    memo: str = ""


class AwardRequest(BaseModel):
    to_id: str
    amount: float
    reason: str = ""
    by: str = "system"


class PenaltyRequest(BaseModel):
    agent_id: str
    amount: float
    reason: str = ""
    by: str = "system"


class JobCreateRequest(BaseModel):
    title: str
    body: str
    reward: float = 10.0
    created_by: str = "human"
    ratings: Optional[dict] = None
    auto_reward: bool = False
    parent_job_id: Optional[str] = None


class JobClaimRequest(BaseModel):
    agent_id: str


class JobSubmitRequest(BaseModel):
    agent_id: str
    submission: str


class JobCancelRequest(BaseModel):
    by: str = "human"
    note: str = ""


class PurgeCancelledJobsRequest(BaseModel):
    by: str = "human"
    note: str = ""
    older_than_seconds: float = 0.0
    limit: int = 5000


class JobUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    reward: Optional[float] = None
    ratings: Optional[dict] = None
    auto_reward: bool = False
    by: str = "human"
    force: bool = False


class JobReviewRequest(BaseModel):
    approved: bool
    reviewed_by: str = "human"
    note: str = ""
    payout: Optional[float] = None
    penalty: Optional[float] = None


class JobVerifyRequest(BaseModel):
    by: str = "human"
    force: bool = False


class CreateEventRequest(BaseModel):
    title: str
    description: str = ""
    location_id: str
    start_day: int
    start_minute: int
    duration_min: int = 60
    created_by: str = "human"


class InviteRequest(BaseModel):
    from_agent_id: str
    to_agent_id: str
    message: str = ""


class RsvpRequest(BaseModel):
    agent_id: str
    status: RsvpStatus
    note: str = ""


class TraceEventRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    kind: TraceKind = "action"
    summary: str
    data: dict = Field(default_factory=dict)


class WebFetchRequest(BaseModel):
    agent_id: str = "unknown"
    agent_name: str = ""
    url: str
    timeout_seconds: Optional[float] = None
    max_bytes: Optional[int] = None


class WebSearchRequest(BaseModel):
    agent_id: str = "unknown"
    agent_name: str = ""
    query: str
    num: int = 10


class MemoryAppendRequest(BaseModel):
    kind: MemoryKind = "note"
    text: str
    tags: List[str] = Field(default_factory=list)
    importance: Optional[float] = None


class TopicSetRequest(BaseModel):
    topic: str
    by_agent_id: str
    by_agent_name: str
    reason: str = ""


class RecordActionRequest(BaseModel):
    action_kind: str = ""


class NewRunRequest(BaseModel):
    run_id: str = ""
    reset_board: bool = True
    reset_topic: bool = True


class OpportunityUpdateRequest(BaseModel):
    fingerprint: str = ""
    status: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    client_response: Optional[str] = None
    outcome: Optional[str] = None


class ClientResponseRequest(BaseModel):
    fingerprint: str
    email_content: str
    simulate_delay_hours: Optional[float] = 24.0


class ArtifactPutRequest(BaseModel):
    job_id: str
    path: str
    content: str
    content_type: str = "text/plain"


class PayPalWebhookRequest(BaseModel):
    event_type: str
    resource: dict
    id: str = ""
    create_time: str = ""


class AdminChatSayRequest(BaseModel):
    sender_id: str
    sender_name: str = ""
    text: str
