"""Write wide date/post tables from SQLite to XLSX without retaining all cells."""

from datetime import datetime
from pathlib import Path
from threading import Event

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet._writer import WorksheetWriter

from app.core.timezone import to_tashkent
from app.reports.post_excel import _safe
from app.services.post_range import decode

META = ["Telegram ID", "Kanal / guruh nomi", "Turi", "Kanal / guruh havolasi"]
SOURCE = ["Post havolasi", "Chiqarilgan vaqt (Toshkent)", "Obunachilar", "Ko'rishlar", "Reaksiyalar",
          "Ulashishlar", "Izohlar", "Public Shares", "Private Shares", "Olingan vaqt (Toshkent)"]
FORWARD = ["Forward havolasi", "Chiqarilgan vaqt (Toshkent)", "Obunachilar / a'zolar",
           "Ko'rishlar", "Reaksiyalar", "Ulashishlar", "Izohlar"]
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="24476A")
BODY_FONT = Font(name="Calibri", size=11)
ALIGN = Alignment(vertical="center", wrap_text=True)


class RangeExportCancelled(Exception):
    pass


class DiskWorksheetWriter(WorksheetWriter):
    """Keep streaming XML on the job's disk, rather than a possibly RAM-backed /tmp."""

    def cleanup(self):
        Path(self.out).unlink(missing_ok=True)


def _local(value):
    return to_tashkent(value).replace(tzinfo=None) if value else None


def _blocks(db, forwards, post_offset=0, post_limit=-1):
    for source_id, day in db.execute("SELECT message_id,day FROM posts ORDER BY day,seq LIMIT ? OFFSET ?", (post_limit, post_offset)):
        slots = 1
        if forwards:
            slots = db.execute("SELECT COALESCE(MAX(n),1) FROM (SELECT COUNT(*) n FROM forwards WHERE source_id=? GROUP BY destination_id)",
                               (source_id,)).fetchone()[0]
        for slot in range(slots):
            yield source_id, day, slot


def _sections(blocks, fields, max_columns):
    capacity = max(1, (max_columns - len(META)) // len(fields))
    section = []
    for block in blocks:
        section.append(block)
        if len(section) == capacity:
            yield section
            section = []
    if section:
        yield section


def _cells(ws, values, header=False):
    for value in values:
        value = _safe(value)
        cell = WriteOnlyCell(ws, value=value)
        if isinstance(value, str):
            cell.data_type = "s"
        cell.font = HEADER_FONT if header else BODY_FONT
        cell.alignment = ALIGN
        if header:
            cell.fill = HEADER_FILL
        elif isinstance(value, int):
            cell.number_format = "#,##0"
        elif isinstance(value, datetime):
            cell.number_format = "dd.mm.yyyy hh:mm"
        # URLs stay as text: embedded hyperlink relationships accumulate in RAM
        # even in openpyxl's write-only mode on very large reports.
        yield cell


def _sheet(wb, title, section, fields, path):
    ws = wb.create_sheet(title)
    for number, width in enumerate((23, 32, 14, 40), 1):
        ws.column_dimensions[get_column_letter(number)].width = width
    headers = list(META)
    for source_id, day, slot in section:
        suffix = f" · nusxa {slot + 1}" if slot else ""
        headers.extend(f"{day} · Post #{source_id}{suffix}\n{field}" for field in fields)
    for column in range(len(META) + 1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(column)].width = 26
    ws.freeze_panes = "E2"
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 58
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    ws._writer = DiskWorksheetWriter(ws, str(Path(path).with_suffix(f".sheet{len(wb.worksheets)}.xml")))
    ws._writer.write_top()
    ws.append(_cells(ws, headers, header=True))
    return ws


def generate_post_range_excel(store, path, stop: Event, *, max_columns=16384,
                             destination_offset=0, destination_limit=-1, post_offset=0, post_limit=-1):
    """Only one output row and one bounded block header are materialized at a time."""
    wb = Workbook(write_only=True)
    try:
        for forwards, fields, prefix in ((False, SOURCE, "Asosiy postlar"), (True, FORWARD, "Public forwardlar")):
            blocks = _sections(_blocks(store.db, forwards, post_offset, post_limit), fields, max_columns)
            for number, section in enumerate(blocks, 1):
                if stop.is_set():
                    break
                title = prefix + (" qisman" if store.partial_count or not store.collection_complete else "")
                if number > 1:
                    title += f" {number}"
                ws = _sheet(wb, title, section, fields, path)
                row_count = 1
                if not forwards:
                    first = store.db.execute("SELECT source FROM posts ORDER BY seq LIMIT 1").fetchone()
                    post = decode(first[0])
                    values = [post.telegram_id, post.title, post.kind, post.channel_url]
                    for source_id, _, _ in section:
                        data, public, private, checked = store.db.execute(
                            "SELECT source,public,private,checked FROM posts WHERE message_id=?", (source_id,)).fetchone()
                        post = decode(data)
                        values.extend([post.post_url, _local(post.published_at), post.members, post.views,
                                       post.reactions, post.shares, post.replies, public, private,
                                       _local(datetime.fromisoformat(checked))])
                    ws.append(_cells(ws, values))
                    row_count += 1
                else:
                    # SQLite INTEGER order is numeric, independent of title or username.
                    for destination in store.db.execute("SELECT id,title,kind,url FROM destinations ORDER BY id LIMIT ? OFFSET ?",
                                                        (destination_limit, destination_offset)):
                        if stop.is_set():
                            break
                        values = list(destination)
                        for source_id, _, slot in section:
                            row = store.db.execute("""SELECT payload FROM forwards WHERE source_id=? AND destination_id=?
                                ORDER BY published,message_id LIMIT 1 OFFSET ?""", (source_id, destination[0], slot)).fetchone()
                            if row:
                                post = decode(row[0])
                                values.extend([post.post_url, _local(post.published_at), post.members, post.views,
                                               post.reactions, post.shares, post.replies])
                            else:
                                values.extend([None] * len(fields))
                        ws.append(_cells(ws, values))
                        row_count += 1
                ws.auto_filter.ref = f"A1:{get_column_letter(len(META) + len(section) * len(fields))}{row_count}"
        if not wb.worksheets:
            wb.create_sheet("Hisobot")
        if stop.is_set():
            raise RangeExportCancelled()
        # Saving also cleans openpyxl's temporary worksheet XML files after cancellation.
        wb.save(path)
    finally:
        wb.close()
        for ws in wb.worksheets:
            writer = getattr(ws, "_writer", None)
            if writer is not None:
                try:
                    if not ws.closed:
                        ws.close()
                finally:
                    writer.cleanup()
    if stop.is_set():
        raise RangeExportCancelled()
