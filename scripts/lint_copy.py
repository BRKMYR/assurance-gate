#!/usr/bin/env python3
"""Copy linter and stealth grep. See docs/ARCHITECTURE.md section 10.

Two modes. Push mode allows `[[OWNER_COPY: slot]]` placeholders and runs on
every push. Release mode treats a placeholder as a violation and runs on a tag.

Usage:

    python scripts/lint_copy.py --mode push [paths...]

With no paths the default set from section 10 is used. Exit code 0 when clean,
1 when any violation was found, 2 on a bad invocation. Warnings never change
the exit code.
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

# Default prose paths, section 10.
DEFAULT_PROSE_GLOBS: tuple[str, ...] = (
    "README.md",
    "space/README.md",
    "dataset/README.md",
    "site/strings.json",
    "gates/*.yaml",
    "external/**/*.md",
    "external/**/*.html",
    "external/**/*.patch",
)

# Stealth grep reaches wider, section 10.
STEALTH_ROOTS: tuple[str, ...] = ("site", "runs", "space", "dataset", "external")
#: Third party viewer code shipped inside the Inspect bundle is not our copy.
STEALTH_SKIP_PREFIXES: tuple[str, ...] = ("site/inspect/assets/",)
STEALTH_EXTRA_FILES: tuple[str, ...] = ("README.md",)

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".woff", ".woff2", ".ttf", ".otf", ".eval", ".zip", ".gz",
}

PLACEHOLDER = "[[OWNER_COPY"


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str
    warning: bool = False

    def render(self) -> str:
        kind = "warning" if self.warning else "violation"
        return f"{self.path}:{self.line}: {self.rule}: {kind}: {self.excerpt}"


@dataclass(frozen=True)
class Segment:
    """One line of prose, already stripped of code, markup and links."""

    line: int
    text: str
    key: str | None = None


def excerpt_of(text: str, limit: int = 90) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# --------------------------------------------------------------------------
# Masking helpers. Masking keeps line numbers intact.
# --------------------------------------------------------------------------


def mask(text: str, pattern: re.Pattern[str]) -> str:
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return pattern.sub(blank, text)


RE_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
RE_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
RE_INLINE_CODE = re.compile(r"`[^`\n]*`")
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
RE_URL = re.compile(r"https?://\S+|mailto:\S+")
RE_MD_LINK_TARGET = re.compile(r"\]\([^)]*\)")
RE_MD_MARKER = re.compile(r"^[ \t]*(?:[-*+>]\s+|\d+\.\s+|#{1,6}\s+)", re.MULTILINE)
RE_MD_EMPHASIS = re.compile(r"\*\*|[*#|]")
RE_MD_TABLE_DIVIDER = re.compile(r"^[ \t]*\|?[ \t:|-]+\|[ \t:|-]*$", re.MULTILINE)
RE_SCRIPT = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
RE_STYLE = re.compile(r"<style\b.*?</style>", re.DOTALL | re.IGNORECASE)
RE_SVG = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
RE_TAG = re.compile(r"<[^>]*>", re.DOTALL)
RE_META_DESCRIPTION = re.compile(
    r"<meta\s+name=\"description\"\s+content=\"([^\"]*)\"\s*/?>", re.IGNORECASE
)


def segments_from_masked(text: str, key: str | None = None) -> list[Segment]:
    out: list[Segment] = []
    for index, raw in enumerate(text.split("\n"), start=1):
        line = html_module.unescape(raw).strip()
        if line:
            out.append(Segment(index, line, key))
    return out


def extract_markdown(text: str) -> list[Segment]:
    masked = mask(text, RE_FRONT_MATTER)
    masked = mask(masked, RE_FENCE)
    masked = mask(masked, RE_HTML_COMMENT)
    masked = mask(masked, RE_INLINE_CODE)
    masked = mask(masked, RE_URL)
    masked = mask(masked, RE_MD_LINK_TARGET)
    masked = mask(masked, RE_MD_TABLE_DIVIDER)
    masked = mask(masked, RE_TAG)
    masked = mask(masked, RE_MD_MARKER)
    masked = mask(masked, RE_MD_EMPHASIS)
    return segments_from_masked(masked)


def extract_html(text: str) -> list[Segment]:
    extra: list[Segment] = []
    for match in RE_META_DESCRIPTION.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        extra.append(Segment(line, html_module.unescape(match.group(1)).strip()))
    masked = mask(text, RE_HTML_COMMENT)
    masked = mask(masked, RE_SCRIPT)
    masked = mask(masked, RE_STYLE)
    masked = mask(masked, RE_SVG)
    masked = mask(masked, RE_URL)
    masked = mask(masked, RE_TAG)
    return sorted(extra + segments_from_masked(masked), key=lambda s: s.line)


def extract_json(text: str) -> list[Segment]:
    """Only string values of `strings.json` style files are prose."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    lines = text.split("\n")
    out: list[Segment] = []

    def line_of(value: str) -> int:
        needle = json.dumps(value)[1:-1][:40]
        for index, line in enumerate(lines, start=1):
            if needle and needle in line:
                return index
        return 1

    def walk(node: object, key: str) -> None:
        if isinstance(node, dict):
            for name, child in node.items():
                walk(child, f"{key}.{name}" if key else str(name))
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str):
            cleaned = html_module.unescape(mask(node, RE_URL)).strip()
            if cleaned:
                out.append(Segment(line_of(node), cleaned, key))

    walk(data, "")
    return out


RE_YAML_COPY_FIELD = re.compile(r"^\s*(rationale|source)\s*:\s*(.*)$")


def extract_yaml(text: str) -> list[Segment]:
    out: list[Segment] = []
    for index, raw in enumerate(text.split("\n"), start=1):
        match = RE_YAML_COPY_FIELD.match(raw)
        if not match:
            continue
        value = match.group(2).strip().strip("'\"").strip()
        if value:
            out.append(Segment(index, value, match.group(1)))
    return out


def extract_text(text: str) -> list[Segment]:
    return segments_from_masked(mask(text, RE_URL))


EXTRACTORS: dict[str, Callable[[str], list[Segment]]] = {
    ".md": extract_markdown,
    ".markdown": extract_markdown,
    ".html": extract_html,
    ".htm": extract_html,
    ".json": extract_json,
    ".yaml": extract_yaml,
    ".yml": extract_yaml,
    ".txt": extract_text,
}


RE_PATCH_TARGET = re.compile(r"^\+\+\+ b/(.*)$")


def patch_added_text(text: str) -> tuple[str, dict[str, str]]:
    """Return the added lines of a patch, grouped by target file.

    Only added content lines are linted. Patch metadata (author, subject,
    index lines, the diff stat and the git version footer) is not copy that
    ships anywhere, and the author line carries a git identity address that
    the stealth rule would otherwise read as a leaked email.
    """
    per_target: dict[str, list[str]] = {}
    blank = " " * 0
    target = ""
    lines = text.split("\n")
    for raw in lines:
        if raw.startswith("+++ b/"):
            match = RE_PATCH_TARGET.match(raw)
            target = match.group(1) if match else ""
            per_target.setdefault(target, [])
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            per_target.setdefault(target, []).append(raw[1:])
        else:
            per_target.setdefault(target, []).append(blank)
    joined = {name: "\n".join(body) for name, body in per_target.items()}
    added_only = "\n".join(
        raw[1:] for raw in lines if raw.startswith("+") and not raw.startswith("+++")
    )
    return added_only, joined


def extract_patch(text: str) -> list[Segment]:
    """Lint the added lines of a patch with the extractor of their target."""
    _, per_target = patch_added_text(text)
    out: list[Segment] = []
    lines = text.split("\n")
    target_of_line: list[str] = []
    current = ""
    for raw in lines:
        if raw.startswith("+++ b/"):
            match = RE_PATCH_TARGET.match(raw)
            current = match.group(1) if match else ""
        target_of_line.append(current)
    # Reconstruct per target with patch line numbers preserved.
    for name, body in per_target.items():
        suffix = Path(name).suffix.lower()
        extractor = EXTRACTORS.get(suffix, extract_text)
        # Rebuild a text of the same line count as the patch so that the
        # extractor's line numbers are the patch's line numbers.
        rebuilt: list[str] = []
        for index, raw in enumerate(lines):
            if target_of_line[index] == name and raw.startswith("+") and not raw.startswith("+++"):
                rebuilt.append(raw[1:])
            else:
                rebuilt.append("")
        out.extend(extractor("\n".join(rebuilt)))
    return sorted(out, key=lambda s: s.line)


EXTRACTORS[".patch"] = extract_patch
EXTRACTORS[".diff"] = extract_patch


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

RE_EM_DASH = re.compile("—")
RE_EN_DASH_AS_DASH = re.compile(r"(?<!\d)–|–(?!\d)")
RE_SEMICOLON = re.compile(r";")
RE_EXCLAMATION = re.compile(r"!")
RE_QUESTION = re.compile(r"\?")

HYPHEN_TOKEN = re.compile(r"[A-Za-z][\w']*(?:-[\w']*[A-Za-z][\w']*)+")
HYPHEN_ALLOW_LITERAL = {
    "data.json",
    "gates.yaml",
    "strong_reject",
    "xstest",
    "post-hoc",
    "assurance-gate",  # the repository and distribution name
}
HYPHEN_ALLOW_PATTERNS = (re.compile(r"^AC-\d+$"), re.compile(r"^\d{4}-\d{2}-\d{2}$"))

BANNED_WORDS = (
    "seamless",
    "robust",
    "leverage",
    "delve",
    "comprehensive",
    "spearheaded",
    "pioneered",
    "muscle",
)
BANNED_PHRASES = ("cutting edge", "deeply resonates", "meaningful impact", "I bring")
RE_BANNED_WORDS = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.IGNORECASE)
RE_BANNED_PHRASES = re.compile(r"(" + "|".join(BANNED_PHRASES) + r")", re.IGNORECASE)

RE_CONSTRUCTIONS = (
    re.compile(r"\b\w+, not \w+"),
    re.compile(r", rather than"),
    re.compile(r"\bThat is the point\b"),
    re.compile(r"\bthe whole point\b"),
    re.compile(r"\bproves nothing\b"),
)

SELF_CERT_WORDS = (
    "honestly",
    "clearly",
    "obviously",
    "simply",
    "actual",
    "actually",
    "genuinely",
    "truly",
    "realistically",
)
RE_SELF_CERT = re.compile(r"\b(" + "|".join(SELF_CERT_WORDS) + r")\b", re.IGNORECASE)
RE_SELF_CERT_REAL = re.compile(r"\breal\s+(story|state|argument|release)\b", re.IGNORECASE)

RE_OWNER_COPY = re.compile(r"\[\[OWNER_COPY")

STEALTH_INSENSITIVE = (
    "Helsing",
    "Barkmeyer",
    "Jonsson",
    "niklas",
    "Automated Driving Zones",
    "ADZ",
    "Confidence Indicator",
    "MCI",
    "Airbus",
    "Siemens",
    "UP42",
    "TerraLoupe",
)
RE_STEALTH_INSENSITIVE = re.compile(
    "|".join(r"\b" + re.escape(term) + r"\b" for term in STEALTH_INSENSITIVE), re.IGNORECASE
)
RE_STEALTH_SENSITIVE = re.compile(r"HERE Technologies")
RE_STEALTH_2M = re.compile(r"\b2M\b")
RE_STEALTH_USERS = re.compile(r"/Users/")
RE_STEALTH_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Approximate adjective list for the three in a row warning.
ADJECTIVES = {
    "big", "small", "fast", "slow", "new", "old", "clear", "simple", "complex",
    "safe", "unsafe", "hard", "soft", "quick", "clean", "dirty", "long", "short",
    "strong", "weak", "high", "low", "wide", "narrow", "bright", "dark", "deep",
    "shallow", "rich", "poor", "modern", "classic", "smart", "heavy", "light",
}

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
ENUMERATION_SPLIT = re.compile(r"[:,]")
RE_WORD = re.compile(r"[A-Za-z0-9][\w'./_-]*")

MAX_SENTENCE_WORDS = 30
MAX_AVERAGE_WORDS = 18
WARN_ONLY_KEYS = {"owner.limitations"}


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for sentence in SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        colon_parts = sentence.split(":")
        if len(colon_parts) > 1 and len(colon_parts[-1].split(",")) >= 3:
            out.extend(part.strip() for part in ENUMERATION_SPLIT.split(sentence) if part.strip())
        else:
            out.append(sentence)
    return out


def _word_count(text: str) -> int:
    return len(RE_WORD.findall(text))


def check_segments(path: str, segments: Sequence[Segment], mode: str) -> list[Finding]:
    findings: list[Finding] = []
    total_words = 0
    total_sentences = 0

    def add(segment: Segment, rule: str, warning: bool = False) -> None:
        findings.append(Finding(path, segment.line, rule, excerpt_of(segment.text), warning))

    for segment in segments:
        text = segment.text
        warn_only = segment.key in WARN_ONLY_KEYS
        if RE_EM_DASH.search(text) or RE_EN_DASH_AS_DASH.search(text):
            add(segment, "em_dash")
        if RE_SEMICOLON.search(text):
            add(segment, "semicolon")
        if RE_EXCLAMATION.search(text):
            add(segment, "exclamation")
        if RE_QUESTION.search(text):
            add(segment, "rhetorical_question")
        for token in HYPHEN_TOKEN.findall(text):
            if "/" in token or token in HYPHEN_ALLOW_LITERAL:
                continue
            if any(pattern.match(token) for pattern in HYPHEN_ALLOW_PATTERNS):
                continue
            findings.append(Finding(path, segment.line, "hyphen_compound", token))
        if RE_BANNED_WORDS.search(text) or RE_BANNED_PHRASES.search(text):
            add(segment, "banned_word")
        if any(pattern.search(text) for pattern in RE_CONSTRUCTIONS):
            add(segment, "construction")
        words = [word.lower() for word in RE_WORD.findall(text)]
        for index in range(len(words) - 2):
            if all(word in ADJECTIVES for word in words[index : index + 3]):
                add(segment, "construction", warning=True)
                break
        if RE_SELF_CERT.search(text) or RE_SELF_CERT_REAL.search(text):
            add(segment, "self_certifying")
        if RE_OWNER_COPY.search(text) and mode == "release":
            add(segment, "owner_copy")

        for sentence in _sentences(text):
            count = _word_count(sentence)
            total_words += count
            total_sentences += 1
            if count > MAX_SENTENCE_WORDS:
                findings.append(
                    Finding(path, segment.line, "sentence_length", excerpt_of(sentence), warn_only)
                )
        sentences = _sentences(text)
        if sentences and _word_count(sentences[-1]) < 6 and text.endswith((".", "!", "?")):
            add(segment, "construction", warning=True)

    if total_sentences:
        average = total_words / total_sentences
        if average > MAX_AVERAGE_WORDS:
            findings.append(
                Finding(
                    path,
                    1,
                    "sentence_length",
                    f"average sentence {average:.1f} words over {total_sentences} sentences",
                )
            )
    return findings


def check_stealth(path: str, text: str, suffix: str) -> list[Finding]:
    """Stealth grep over raw content. Patches are checked on added lines only."""
    if suffix in {".patch", ".diff"}:
        lines: list[tuple[int, str]] = [
            (index, raw[1:])
            for index, raw in enumerate(text.split("\n"), start=1)
            if raw.startswith("+") and not raw.startswith("+++")
        ]
    else:
        lines = list(enumerate(text.split("\n"), start=1))

    findings: list[Finding] = []
    for index, raw in lines:
        for pattern in (
            RE_STEALTH_INSENSITIVE,
            RE_STEALTH_SENSITIVE,
            RE_STEALTH_2M,
            RE_STEALTH_USERS,
            RE_STEALTH_EMAIL,
        ):
            match = pattern.search(raw)
            if match:
                findings.append(Finding(path, index, "stealth", excerpt_of(match.group(0))))
    return findings


def check_owner_copy_raw(path: str, text: str, mode: str) -> list[Finding]:
    if mode != "release":
        return []
    findings: list[Finding] = []
    for index, raw in enumerate(text.split("\n"), start=1):
        if PLACEHOLDER in raw:
            findings.append(Finding(path, index, "owner_copy", excerpt_of(raw)))
    return findings


# --------------------------------------------------------------------------
# File collection
# --------------------------------------------------------------------------


def read_text(path: Path) -> str | None:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def iter_files(target: Path) -> Iterator[Path]:
    if target.is_dir():
        for child in sorted(target.rglob("*")):
            if child.is_file() and not any(part.startswith(".") for part in child.parts):
                yield child
    elif target.is_file():
        yield target


def default_prose_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in DEFAULT_PROSE_GLOBS:
        found.extend(sorted(path for path in root.glob(pattern) if path.is_file()))
    return found


def default_stealth_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in STEALTH_ROOTS:
        for path in iter_files(root / name):
            rel = relative(path, root)
            if any(rel.startswith(prefix) for prefix in STEALTH_SKIP_PREFIXES):
                continue
            found.append(path)
    for name in STEALTH_EXTRA_FILES:
        path = root / name
        if path.is_file():
            found.append(path)
    return sorted(set(found))


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def lint(paths: Sequence[Path] | None, mode: str, root: Path = REPO_ROOT) -> list[Finding]:
    if paths:
        prose_files: list[Path] = []
        for target in paths:
            prose_files.extend(iter_files(target))
        stealth_files = list(prose_files)
    else:
        prose_files = default_prose_files(root)
        stealth_files = default_stealth_files(root)

    findings: list[Finding] = []
    for path in sorted(set(prose_files)):
        text = read_text(path)
        if text is None:
            continue
        name = relative(path, root)
        extractor = EXTRACTORS.get(path.suffix.lower())
        if extractor is None:
            continue
        findings.extend(check_segments(name, extractor(text), mode))
    for path in sorted(set(stealth_files)):
        text = read_text(path)
        if text is None:
            continue
        name = relative(path, root)
        findings.extend(check_stealth(name, text, path.suffix.lower()))
        if path not in prose_files or EXTRACTORS.get(path.suffix.lower()) is None:
            findings.extend(check_owner_copy_raw(name, text, mode))
    return sorted(set(findings), key=lambda f: (f.path, f.line, f.rule))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy linter and stealth grep.")
    parser.add_argument("--mode", choices=("push", "release"), required=True)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)

    for target in args.paths:
        if not target.exists():
            print(f"lint_copy: no such path: {target}", file=sys.stderr)
            return 2

    findings = lint(args.paths, args.mode)
    violations = [finding for finding in findings if not finding.warning]
    warnings = [finding for finding in findings if finding.warning]
    for finding in findings:
        print(finding.render())
    print(f"lint_copy --mode {args.mode}: {len(violations)} violations, {len(warnings)} warnings")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
