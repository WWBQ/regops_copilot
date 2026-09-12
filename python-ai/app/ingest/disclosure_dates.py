"""巨潮年报实际披露日（announcementTime，东八区日历日）。

报告期（会计年度）≠ 披露日。来源：cninfo hisAnnouncement，
与 download_annual_pdfs.pick_annual_announcement 同一条全文年报。
"""

from __future__ import annotations

from datetime import date

# doc_id → 披露日。补齐后新 ingest 会写入 pdf_document.disclosure_date。
DISCLOSURE_DATES: dict[str, date] = {
    "002594_2023": date(2024, 3, 27),
    "002594_2024": date(2025, 3, 25),
    "601633_2023": date(2024, 3, 29),
    "601633_2024": date(2025, 3, 29),
    "000333_2023": date(2024, 3, 28),
    "000333_2024": date(2025, 3, 29),
    "000651_2023": date(2024, 4, 30),
    "000651_2024": date(2025, 4, 28),
    "600031_2023": date(2024, 4, 29),
    "600031_2024": date(2025, 4, 18),
    "300750_2023": date(2024, 3, 16),
    "300750_2024": date(2025, 3, 15),
    "600519_2023": date(2024, 4, 3),
    "600519_2024": date(2025, 4, 3),
}


def disclosure_date_for(doc_id: str) -> date | None:
    return DISCLOSURE_DATES.get(doc_id)
