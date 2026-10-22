"""Bounded-memory package checks, independent of openpyxl's tolerant reader."""

from xml.etree.ElementTree import iterparse
from zipfile import ZipFile

from openpyxl.utils.cell import range_boundaries


def validate_xlsx(path):
    """Check CRC, every XML part, and nonempty, consistent Excel table metadata.

    This is structural validation, not a substitute for testing in Excel itself.
    XML elements are released as they are read, including on large worksheets.
    """
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Excel ZIP fayli shikastlangan.")
        required = {"[Content_Types].xml", "xl/workbook.xml", "_rels/.rels"}
        if not required.issubset(archive.namelist()):
            raise ValueError("Excel paketining majburiy qismlari topilmadi.")
        table_names = set()
        for name in archive.namelist():
            if not name.endswith((".xml", ".rels")):
                continue
            with archive.open(name) as part:
                stack = []
                headers, bounds = [], None
                for event, element in iterparse(part, events=("start", "end")):
                    if event == "start":
                        stack.append(element)
                        if name.startswith("xl/tables/"):
                            tag = element.tag.rsplit("}", 1)[-1]
                            if tag == "table":
                                title = element.get("displayName")
                                if not title or title.casefold() in table_names:
                                    raise ValueError("Excel jadval nomi takrorlangan.")
                                table_names.add(title.casefold())
                                bounds = range_boundaries(element.get("ref", ""))
                            elif tag == "tableColumn":
                                headers.append(element.get("name"))
                        continue
                    stack.pop()
                    element.clear()
                    if stack:
                        stack[-1].remove(element)
                if bounds:
                    left, top, right, bottom = bounds
                    if bottom <= top or right - left + 1 != len(headers) or not all(headers):
                        raise ValueError("Excel jadval diapazoni yoki sarlavhalari noto'g'ri.")
                    if len({header.casefold() for header in headers}) != len(headers):
                        raise ValueError("Excel jadval sarlavhalari takrorlangan.")
