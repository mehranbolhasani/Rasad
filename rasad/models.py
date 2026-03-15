"""
مدل‌های داده مشترک برای خط لوله رصد.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """یک مقاله از فید RSS."""
    title: str
    summary: str
    link: str
    source: str
    published: Optional[datetime] = None
    raw_text: str = ""
    is_live: bool = False


@dataclass
class SourceRef:
    """ارجاع به یک مقاله منبع."""
    name: str
    url: str


@dataclass
class GroupedStory:
    """یک خبر گروه‌بندی‌شده از چندین منبع."""
    headline: str
    summary: str
    sources: list[SourceRef] = field(default_factory=list)
    confirmed: bool = False
    published: Optional[datetime] = None
