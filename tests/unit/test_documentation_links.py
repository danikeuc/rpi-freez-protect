import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parents[2]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def github_anchor(heading: str) -> str:
    """Return the GitHub-style anchor used by this repository's headings."""
    heading = re.sub(r"<[^>]+>", "", heading).strip().lower()
    heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s+", "-", heading)


def test_internal_markdown_links_resolve() -> None:
    failures: list[str] = []
    markdown_files = sorted(
        path for path in ROOT.rglob("*.md") if ".git" not in path.parts
    )

    for source in markdown_files:
        text = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, fragment = unquote(target).partition("#")
            destination = source if not file_part else (source.parent / file_part).resolve()
            if not destination.is_file():
                failures.append(f"{source.relative_to(ROOT)} -> missing {target}")
                continue
            if fragment and destination.suffix.lower() == ".md":
                headings = {
                    github_anchor(match) for match in HEADING.findall(
                        destination.read_text(encoding="utf-8")
                    )
                }
                if fragment.lower() not in headings:
                    failures.append(
                        f"{source.relative_to(ROOT)} -> missing anchor {target}"
                    )

    assert not failures, "\n".join(failures)
