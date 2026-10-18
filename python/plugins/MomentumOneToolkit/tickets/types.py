from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

class TicketStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class TicketType:
    SUPPORT = "SUPPORT"
    GENERAL = "GENERAL"
    BUG = "BUG"
    REPORT = "REPORT"

@dataclass
class TicketRecord:
    ticket_id: int
    guild_id: str
    channel_id: str
    creator_id: str
    creator_name: str
    ticket_type: str = TicketType.SUPPORT
    status: str = TicketStatus.OPEN
    subject: str = "General Support"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    closed_at: Optional[float] = None
    closed_by: Optional[str] = None
    transcript: Optional[str] = None

@dataclass
class TicketGuildConfig:
    guild_id: str
    staff_role_ids: List[str] = field(default_factory=list)
    ticket_counter: int = 1000
    enabled: bool = True
    category_id: Optional[str] = None
