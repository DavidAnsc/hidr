#!/usr/bin/env python3
"""Check the repo's Markdown docs.

1. Every relative link or image (Markdown or <img src>) points to a file that exists.
2. Every #anchor link matches a heading in the target file.
3. If PRIVACY.md changed since BASE_REF, its "_Last updated: ..._" line changed too.

Usage: check_docs.py [BASE_REF]
"""
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_SRC = re.compile(r"""<(?:img|a)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
UPDATED = re.compile(r"^_Last updated: .+_$", re.M)


def strip_code(text):
    """Blank out fenced blocks and inline code so links inside them are ignored."""
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")
        elif in_fence:
            out.append("")
        else:
            out.append(re.sub(r"`[^`]*`", "", line))
    return out


def slugify(heading):
    """GitHub-style heading anchor."""
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path, cache={}):
    if path not in cache:
        seen, result = {}, set()
        for line in strip_code(path.read_text(encoding="utf-8")):
            m = HEADING.match(line)
            if not m:
                continue
            slug = slugify(m.group(2))
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            result.add(slug if n == 0 else f"{slug}-{n}")
        cache[path] = result
    return cache[path]


def check_links(md_files):
    errors = []
    for md in md_files:
        rel = md.relative_to(ROOT)
        for lineno, line in enumerate(strip_code(md.read_text(encoding="utf-8")), 1):
            for target in MD_LINK.findall(line) + HTML_SRC.findall(line):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
                    continue  # external URL, mailto:, etc.
                path_part, _, frag = target.partition("#")
                dest = (md.parent / unquote(path_part)).resolve() if path_part else md
                where = f"{rel}:{lineno}"
                if not dest.exists():
                    errors.append(f"{where}: broken link '{target}'")
                elif ROOT not in dest.parents and dest != ROOT:
                    errors.append(f"{where}: link leaves the repo '{target}'")
                elif frag and dest.suffix.lower() == ".md" and unquote(frag).lower() not in anchors(dest):
                    errors.append(f"{where}: no heading for anchor '#{frag}'")
    return errors


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def check_privacy_date(base):
    if not base or git("rev-parse", "--verify", "--quiet", base).returncode != 0:
        return []
    if not git("diff", "--quiet", base, "--", "PRIVACY.md").returncode:
        return []  # unchanged
    old = git("show", f"{base}:PRIVACY.md")
    if old.returncode != 0:
        return []  # file is new
    new = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    old_date, new_date = UPDATED.search(old.stdout), UPDATED.search(new)
    if not new_date:
        return ["PRIVACY.md: missing '_Last updated: ..._' line"]
    if old_date and old_date.group(0) == new_date.group(0):
        return ["PRIVACY.md changed but its 'Last updated' date did not"]
    return []


def main():
    md_files = sorted(p for p in ROOT.rglob("*.md") if ".git" not in p.parts)
    errors = check_links(md_files)
    errors += check_privacy_date(sys.argv[1] if len(sys.argv) > 1 else None)
    for e in errors:
        print(f"::error::{e}")
    print(f"Checked {len(md_files)} Markdown file(s): {len(errors)} problem(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
