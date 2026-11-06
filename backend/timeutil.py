"""Asia/Kolkata is the only business timezone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import Config


def business_tz() -> ZoneInfo:
    return ZoneInfo(Config.BUSINESS_TIMEZONE)


def now_business() -> datetime:
    return datetime.now(business_tz())


def business_date_str(when: datetime | None = None) -> str:
    moment = when or now_business()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=business_tz())
    else:
        moment = moment.astimezone(business_tz())
    return moment.date().isoformat()


def parse_business_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value
