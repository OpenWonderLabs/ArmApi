"""Check generated Conda download pages against repodata and local link targets."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class DownloadPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.rows = [], []
        self.row, self.cell = None, None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            if self.row is not None:
                self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = None


def check_conda_html(root: Path) -> list[str]:
    errors = []
    pages = set(root.rglob("index.html"))
    for name in ("repodata.json", "channeldata.json"):
        pages.update(path.with_name("index.html") for path in root.rglob(name))
    for path in sorted(pages):
        try:
            page = DownloadPage()
            page.feed(path.read_text(encoding="utf-8"))
            package_links = []
            for href in page.links:
                url = urlsplit(href)
                if url.scheme or url.netloc:
                    continue
                target = unquote(url.path)
                if not (path.parent / target).exists():
                    errors.append(f"{path}: broken download-page link: {href}")
                if target.endswith((".conda", ".tar.bz2")):
                    package_links.append(target)
            repodata = path.with_name("repodata.json")
            if repodata.exists():
                data = json.loads(repodata.read_text(encoding="utf-8"))
                packages = {**data.get("packages", {}), **data.get("packages.conda", {})}
                if sorted(package_links) != sorted(packages):
                    errors.append(f"{path}: HTML package links differ from repodata")
                # The release download template has Package, Bytes, SHA256, MD5 columns.
                expected = [[name, str(meta["size"]), meta["sha256"], meta["md5"]]
                            for name, meta in packages.items()]
                if sorted(page.rows) != sorted(expected):
                    errors.append(f"{path}: HTML package names, sizes or checksums differ from repodata")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{path}: cannot verify download page: {exc}")
    return errors
