#!/usr/bin/env python3
"""Prepare a Markdown article as a Chirpy post."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


_FIELD = re.compile(r"(?P<key>[A-Za-z][A-Za-z0-9_-]*):(?P<value>.*)")
_KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PERMALINK_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_CHINESE_TAG = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \+0800$")
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_RADIX_NUMBER = re.compile(r"^[+-]?0(?:[xX][0-9A-Fa-f]+|[oO][0-7]+|[bB][01]+)$")
_REQUIRED_FIELDS = ("title", "date", "categories", "tags", "description")
_REQUEST_FIELDS = {
    "repo",
    "input",
    "title",
    "categories",
    "tags",
    "description",
    "slug",
    "date",
    "branch",
}
_LEGACY_FIELDS = (
    "repo",
    "input",
    "title",
    "categories",
    "tags",
    "description",
    "slug",
    "date",
    "branch",
)


class FrontMatter(dict[str, object]):
    """Parsed values plus the raw YAML that must survive normalization."""

    def __init__(
        self,
        *args: object,
        preserved: str = "",
        inline_comments: dict[str, str] | None = None,
        seen_keys: set[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preserved = preserved
        self.inline_comments = dict(inline_comments or {})
        self.seen_keys = set(seen_keys if seen_keys is not None else self)


def split_front_matter(source: str) -> tuple[dict[str, object], str]:
    """Return parsed leading Front Matter and the untouched Markdown body."""
    if not isinstance(source, str):
        raise TypeError("source must be a string")

    lines = source.splitlines(keepends=True)
    if not lines or _line_text(lines[0]) != "---":
        return {}, source

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if _line_text(line) == "---":
            end = index
            break
    if end is None:
        raise ValueError("unclosed Front Matter")

    content_lines = lines[1:end]
    metadata = FrontMatter()
    preserved: list[str] = []
    inline_comments: dict[str, str] = {}
    seen_keys: set[str] = set()
    index = 0
    while index < len(content_lines):
        line = content_lines[index]
        text = _line_text(line)
        if _is_blank_or_comment(text):
            preserved.append(line)
            index += 1
            continue
        if text.startswith((" ", "\t", "-")):
            raise ValueError("malformed Front Matter field")

        match = _FIELD.fullmatch(text)
        if not match:
            raise ValueError("malformed Front Matter field")
        key = match["key"]
        if key in seen_keys:
            raise ValueError(f"duplicate Front Matter field: {key}")
        seen_keys.add(key)

        next_index = index + 1
        while next_index < len(content_lines):
            candidate = _line_text(content_lines[next_index])
            if not candidate.startswith((" ", "\t", "-")) and _FIELD.fullmatch(candidate):
                break
            next_index += 1
        continuations = content_lines[index + 1 : next_index]
        semantic_continuations = [
            candidate
            for candidate in continuations
            if not _is_blank_or_comment(_line_text(candidate))
        ]
        value, inline_comment = _split_inline_comment(match["value"])

        if key in _REQUIRED_FIELDS:
            if semantic_continuations or not value:
                raise ValueError(
                    f"unsupported block or nested value for required Front Matter field: {key}"
                )
            try:
                metadata[key] = (
                    parse_list(value) if value.startswith("[") else yaml_scalar(value)
                )
            except ValueError as error:
                raise ValueError(
                    f"unsupported value for required Front Matter field: {key}"
                ) from error
            if inline_comment:
                inline_comments[key] = inline_comment
            preserved.extend(continuations)
        else:
            preserved.extend(content_lines[index:next_index])
            if not semantic_continuations and value:
                try:
                    parsed = (
                        parse_list(value)
                        if value.startswith("[")
                        else yaml_scalar(value)
                    )
                except ValueError:
                    pass
                else:
                    metadata[key] = parsed
        index = next_index

    metadata.preserved = "".join(preserved)
    metadata.inline_comments = inline_comments
    metadata.seen_keys = seen_keys

    body_start = sum(len(line) for line in lines[: end + 1])
    return metadata, source[body_start:]


def normalize_slug(value: str) -> str:
    """Normalize an ASCII slug, rejecting values outside kebab-case."""
    if not isinstance(value, str):
        raise TypeError("slug must be a string")

    slug = re.sub(r"[_\s]+", "-", value.strip().lower())
    if not _KEBAB_CASE.fullmatch(slug):
        raise ValueError("slug must be ASCII kebab-case")
    return slug


def normalize_tags(values: list[str]) -> list[str]:
    """Lowercase, hyphenate, and case-insensitively deduplicate tags."""
    if not isinstance(values, list):
        raise TypeError("tags must be a list")

    normalized_tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("each tag must be a string")
        tag = re.sub(r"[_\s]+", "-", value.strip().lower())
        if not tag:
            raise ValueError("tags cannot be empty")
        if not (_KEBAB_CASE.fullmatch(tag) or _CHINESE_TAG.fullmatch(tag)):
            raise ValueError("tags must be ASCII kebab-case or concise Chinese")
        identity = tag.casefold()
        if identity not in seen:
            seen.add(identity)
            normalized_tags.append(tag)
    return normalized_tags


def parse_list(value: str) -> list[str]:
    """Parse a single-line YAML-style bracket list of scalar strings."""
    if not isinstance(value, str):
        raise TypeError("list value must be a string")
    if "\n" in value or "\r" in value:
        raise ValueError("multiline YAML constructs are not supported")

    text = value.strip()
    if not text.startswith("[") or not text.endswith("]"):
        raise ValueError("malformed YAML list")
    inner = text[1:-1].strip()
    if not inner:
        return []

    items: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(inner):
        char = inner[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(inner) and inner[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ",":
            items.append(_list_item(inner[start:index]))
            start = index + 1
        elif char in "[]{}":
            raise ValueError("malformed YAML list")
        index += 1
    if quote is not None or escaped:
        raise ValueError("malformed quoted YAML scalar")
    items.append(_list_item(inner[start:]))
    return items


def yaml_scalar(value: str) -> object:
    """Parse one supported single-line YAML scalar."""
    if not isinstance(value, str):
        raise TypeError("YAML scalar must be a string")
    if "\n" in value or "\r" in value:
        raise ValueError("multiline YAML constructs are not supported")

    scalar = value.strip()
    if not scalar:
        raise ValueError("malformed YAML scalar")
    if scalar.startswith('"'):
        try:
            decoded = json.loads(scalar)
        except json.JSONDecodeError as error:
            raise ValueError("malformed quoted YAML scalar") from error
        if not isinstance(decoded, str):
            raise ValueError("YAML scalar must be a string")
        return decoded
    if scalar.startswith("'"):
        if len(scalar) < 2 or not scalar.endswith("'"):
            raise ValueError("malformed quoted YAML scalar")
        inner = scalar[1:-1]
        decoded: list[str] = []
        index = 0
        while index < len(inner):
            if inner[index] != "'":
                decoded.append(inner[index])
                index += 1
            elif index + 1 < len(inner) and inner[index + 1] == "'":
                decoded.append("'")
                index += 2
            else:
                raise ValueError("malformed quoted YAML scalar")
        return "".join(decoded)
    if scalar.startswith(("[", "{", "|", ">", "&", "*", "!", "@", "`")):
        raise ValueError("malformed YAML scalar")
    lowered = scalar.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null" or scalar == "~":
        return None
    if _NUMBER.fullmatch(scalar):
        number = (
            float(scalar)
            if "." in scalar or "e" in lowered
            else int(scalar, 10)
        )
        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError("non-finite YAML numbers are not supported")
        return number
    if _RADIX_NUMBER.fullmatch(scalar):
        raise ValueError("unsupported numeric spelling")
    return scalar


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for deterministic post generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--consume-request", action="store_true")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--categories")
    parser.add_argument("--tags")
    parser.add_argument("--description")
    parser.add_argument("--slug")
    parser.add_argument("--date")
    parser.add_argument("--branch")
    return parser


def arguments_from_cli(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve either one JSON request or the compatible individual flags."""
    if args.consume_request and args.request is None:
        raise ValueError("--consume-request requires --request")
    supplied_legacy = [
        field for field in _LEGACY_FIELDS if getattr(args, field, None) is not None
    ]
    if args.request is not None:
        if supplied_legacy:
            raise ValueError(
                "--request is mutually exclusive with individual CLI flags"
            )
        loaded = _load_request(args.request)
        loaded.consume_request = args.consume_request
        return loaded

    required = [field for field in _LEGACY_FIELDS if field != "branch"]
    missing = [field for field in required if getattr(args, field, None) is None]
    if missing:
        shown = ", ".join(f"--{field}" for field in missing)
        raise ValueError(f"missing required individual arguments: {shown}")
    if args.branch is None:
        args.branch = "main"
    return args


def current_branch(repo: Path) -> str:
    """Return the checked-out Git branch for *repo*."""
    result = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or "unable to read current Git branch"
        raise ValueError(diagnostic)
    return result.stdout.strip()


def validate_repo(repo: Path, allowed_branch: str) -> None:
    """Validate the Chirpy repository shape and checked-out branch."""
    if not repo.is_dir():
        raise ValueError(f"repository is not a directory: {repo}")

    resolved_repo = repo.resolve(strict=True)
    required_files = ("_config.yml", "Gemfile", "tools/run.sh")
    for relative_path in required_files:
        if not (resolved_repo / relative_path).is_file():
            raise ValueError(f"missing required Chirpy file: {relative_path}")
    posts = resolved_repo / "_posts"
    if posts.is_symlink():
        raise ValueError("required Chirpy directory must not be a symlink: _posts")
    if not posts.is_dir():
        raise ValueError("missing required Chirpy directory: _posts")
    resolved_posts = posts.resolve(strict=True)
    try:
        resolved_posts.relative_to(resolved_repo)
    except ValueError as error:
        raise ValueError("resolved _posts directory escapes the repository") from error

    branch = current_branch(resolved_repo)
    if branch != allowed_branch:
        shown_branch = branch or "detached HEAD"
        raise ValueError(f"branch {shown_branch!r} is not allowed; expected {allowed_branch!r}")


def merge_metadata(
    existing: dict[str, object], supplied: dict[str, object]
) -> dict[str, object]:
    """Merge required metadata, preserving explicit input values and key order."""
    merged = FrontMatter(
        preserved=getattr(existing, "preserved", ""),
        inline_comments=getattr(existing, "inline_comments", {}),
        seen_keys=getattr(existing, "seen_keys", set(existing)),
    )
    for key in _REQUIRED_FIELDS:
        if key in existing:
            merged[key] = existing[key]
        elif key in supplied:
            merged[key] = supplied[key]
        else:
            raise ValueError(f"missing required Front Matter field: {key}")
    for key, value in existing.items():
        if key not in _REQUIRED_FIELDS:
            merged[key] = value
    return merged


def render_post(metadata: dict[str, object], body: str) -> str:
    """Render supported Front Matter followed by the untouched Markdown body."""
    lines = ["---"]
    if isinstance(metadata, FrontMatter):
        keys = [key for key in _REQUIRED_FIELDS if key in metadata]
    else:
        keys = list(metadata)
    comments = getattr(metadata, "inline_comments", {})
    for key in keys:
        rendered = _render_value(metadata[key], key)
        lines.append(f"{key}: {rendered}{comments.get(key, '')}")

    front_matter = "\n".join(lines) + "\n"
    preserved = getattr(metadata, "preserved", "")
    if preserved:
        front_matter += preserved
        if not preserved.endswith(("\n", "\r")):
            front_matter += "\n"
    return front_matter + "---\n" + body


def prepare_post(args: argparse.Namespace) -> dict[str, object]:
    """Validate inputs, generate one post atomically, and return its receipt."""
    repo = args.repo.expanduser().resolve()
    try:
        source_path = args.input.expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"input file does not exist: {args.input}") from error
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise ValueError(f"input must be a non-empty regular file: {source_path}")

    if not isinstance(args.branch, str) or not args.branch:
        raise ValueError("allowed branch cannot be empty")
    validate_repo(repo, args.branch)

    _validated_date(args.date)
    publication_slug = normalize_slug(args.slug)
    supplied = {
        "title": _non_empty(args.title, "title"),
        "date": args.date,
        "categories": _provided_values(args.categories, "categories"),
        "tags": normalize_tags(_provided_values(args.tags, "tags")),
        "description": _non_empty(args.description, "description"),
    }

    with source_path.open("r", encoding="utf-8", newline="") as stream:
        existing, body = split_front_matter(stream.read())
    metadata = merge_metadata(existing, supplied)
    effective_date = _validate_required_metadata(metadata, set(existing))
    effective_slug = _effective_slug(metadata, publication_slug)
    permalink = _effective_permalink(metadata, effective_slug)
    rendered = render_post(metadata, body)
    rendered_bytes = rendered.encode("utf-8")

    posts = (repo / "_posts").resolve(strict=True)
    destination = (
        posts / f"{effective_date.date().isoformat()}-{publication_slug}.md"
    ).resolve()
    try:
        destination.relative_to(posts)
    except ValueError as error:
        raise ValueError("destination escapes the _posts directory") from error

    created = _atomic_write(destination, rendered_bytes)
    return {
        "source": str(source_path),
        "destination": str(destination),
        "permalink": permalink,
        "metadata": metadata,
        "created": created,
    }


def main() -> int:
    """Run the CLI and emit exactly one JSON receipt on success."""
    raw_args = build_parser().parse_args()
    consume_path = (
        raw_args.request.expanduser()
        if raw_args.consume_request and raw_args.request is not None
        else None
    )
    receipt: dict[str, object] | None = None
    failure: Exception | None = None
    try:
        args = arguments_from_cli(raw_args)
        receipt = prepare_post(args)
    except (OSError, TypeError, UnicodeError, ValueError) as error:
        failure = error
    finally:
        if consume_path is not None:
            try:
                consume_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                cleanup_failure = ValueError(
                    f"unable to consume request file {consume_path}: {error}"
                )
                if failure is None:
                    failure = cleanup_failure
                else:
                    failure = ValueError(f"{failure}; {cleanup_failure}")
    if failure is not None:
        print(f"error: {failure}", file=sys.stderr)
        return 1
    assert receipt is not None
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")))
    return 0


def _line_text(line: str) -> str:
    return line.removesuffix("\n").removesuffix("\r")


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _split_inline_comment(value: str) -> tuple[str, str]:
    """Split a YAML inline comment without reinterpreting quoted hash signs."""
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(value):
        char = value[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or value[index - 1].isspace()):
            comment_start = index
            while comment_start > 0 and value[comment_start - 1] in " \t":
                comment_start -= 1
            return value[:comment_start].strip(), value[comment_start:]
        index += 1
    return value.strip(), ""


def _render_value(value: object, key: str) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "[" + ", ".join(
            json.dumps(item, ensure_ascii=False) for item in value
        ) + "]"
    if value is None or isinstance(value, (bool, int, float)):
        try:
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        except ValueError as error:
            raise ValueError(f"unsupported Front Matter value for {key}") from error
    raise ValueError(f"unsupported Front Matter value for {key}")


def _load_request(request_path: Path) -> argparse.Namespace:
    try:
        text = request_path.expanduser().read_text(encoding="utf-8")
        payload = json.loads(text, object_pairs_hook=_unique_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid request file: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")

    keys = set(payload)
    if keys != _REQUEST_FIELDS:
        missing = sorted(_REQUEST_FIELDS - keys)
        extra = sorted(keys - _REQUEST_FIELDS)
        details: list[str] = []
        if missing:
            details.append("missing keys: " + ", ".join(missing))
        if extra:
            details.append("unexpected keys: " + ", ".join(extra))
        raise ValueError("request must contain exact keys (" + "; ".join(details) + ")")

    list_fields = {"categories", "tags"}
    for field in _REQUEST_FIELDS - list_fields:
        if not isinstance(payload[field], str):
            raise ValueError(f"request field {field!r} must be a string")
    for field in list_fields:
        value = payload[field]
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError(f"request field {field!r} must be a list of strings")

    return argparse.Namespace(
        request=request_path,
        repo=Path(payload["repo"]),
        input=Path(payload["input"]),
        title=payload["title"],
        categories=payload["categories"],
        tags=payload["tags"],
        description=payload["description"],
        slug=payload["slug"],
        date=payload["date"],
        branch=payload["branch"],
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"request contains duplicate key: {key}")
        result[key] = value
    return result


def _list_item(value: str) -> str:
    item = value.strip()
    if not item:
        raise ValueError("malformed YAML list")
    parsed = yaml_scalar(item)
    if not isinstance(parsed, str):
        raise ValueError("YAML list items must be strings")
    return parsed


def _validated_date(value: str) -> datetime:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError("date must use YYYY-MM-DD HH:MM:SS +0800 format")
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD HH:MM:SS +0800 format") from error


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} cannot be empty")
    return value


def _csv_values(value: str, field: str) -> list[str]:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    values = [item.strip() for item in value.split(",")]
    if not values or any(not item for item in values):
        raise ValueError(f"{field} must be a non-empty CSV list")
    return values


def _provided_values(value: object, field: str) -> list[str]:
    if isinstance(value, str):
        return _csv_values(value, field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a non-empty list of strings")
    return list(value)


def _effective_permalink(metadata: dict[str, object], slug: str) -> str:
    seen_keys = getattr(metadata, "seen_keys", set(metadata))
    if "permalink" not in seen_keys:
        return f"/posts/{slug}/"
    if "permalink" not in metadata or not isinstance(metadata["permalink"], str):
        raise ValueError("permalink must be a supported string")

    permalink = metadata["permalink"]
    if (
        not permalink.startswith("/")
        or not permalink.endswith("/")
        or "?" in permalink
        or "#" in permalink
        or "\\" in permalink
        or "\x00" in permalink
    ):
        raise ValueError(
            "permalink must be an absolute, query-free, fragment-free directory path"
        )
    middle = permalink[1:-1]
    segments = middle.split("/") if middle else []
    if any(
        not segment
        or segment in {".", ".."}
        or not _PERMALINK_SEGMENT.fullmatch(segment)
        for segment in segments
    ):
        raise ValueError("permalink contains an unsafe path segment")
    return permalink


def _effective_slug(metadata: dict[str, object], supplied_slug: str) -> str:
    seen_keys = getattr(metadata, "seen_keys", set(metadata))
    if "slug" not in seen_keys:
        return supplied_slug
    if "slug" not in metadata or not isinstance(metadata["slug"], str):
        raise ValueError("explicit slug must be a non-empty ASCII kebab-case string")

    explicit_slug = metadata["slug"]
    try:
        normalized = normalize_slug(explicit_slug)
    except ValueError as error:
        raise ValueError(
            "explicit slug must be a non-empty ASCII kebab-case string"
        ) from error
    if normalized != explicit_slug:
        raise ValueError("explicit slug must use strict ASCII kebab-case")
    return explicit_slug


def _validate_required_metadata(
    metadata: dict[str, object], existing_fields: set[str]
) -> datetime:
    for field in ("title", "date", "description"):
        value = metadata[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")

    categories = _required_string_list(
        metadata["categories"],
        "categories",
        trim="categories" not in existing_fields,
    )
    tags = _required_string_list(
        metadata["tags"],
        "tags",
        trim="tags" not in existing_fields,
    )
    metadata["categories"] = categories
    metadata["tags"] = (
        tags if "tags" in existing_fields else normalize_tags(tags)
    )
    return _validated_date(metadata["date"])


def _required_string_list(value: object, field: str, *, trim: bool) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a non-empty list of strings")
    return [item.strip() for item in value] if trim else list(value)


def _atomic_write(destination: Path, content: bytes) -> bool:
    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o644)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, destination)
        except FileExistsError as error:
            if destination.is_file() and destination.read_bytes() == content:
                return False
            raise ValueError(
                f"destination already exists with different content: {destination}"
            ) from error
        return True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
