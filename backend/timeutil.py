"""Asia/Kolkata is the only business timezone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import Config


def business_tz() -> ZoneInfo:
    return ZoneInfo(Config.BUSINESS_TIMEZONE)


def now_business() -> datetime:
    return datetime.now(business_tz())
