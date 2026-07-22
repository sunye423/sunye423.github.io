# Publishing Chirpy Blog Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a personal Codex skill that converts a complete Markdown article into a valid Chirpy post, validates it, starts local preview, and stops before any Git commit or push.

**Architecture:** Codex performs semantic metadata inference according to `SKILL.md`; a Python standard-library script performs deterministic repository checks, Front Matter merging, safe post creation, and JSON reporting. Repository-provided scripts perform Jekyll validation and preview. The skill never changes branches or Git history.

**Tech Stack:** Codex skills, Markdown/YAML, Python 3 standard library, `unittest`, Git, Ruby/Bundler, Jekyll/Chirpy.

## Global Constraints

- Install the skill at `/Users/sunye/.codex/skills/publishing-chirpy-blog`.
- Use `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io` as the initial target blog repository.
- Operate on `main` unless the user explicitly names another branch.
- Never run `git switch`, `git checkout`, `git worktree`, `git stash`, `git add`, `git commit`, or `git push` as part of article publication.
- Preserve the source Markdown and its body bytes.
- Stop after local preview starts; the user owns commit and push.
- Use `apply_patch` for hand-authored file changes.
- Run each test in its failing state before implementing the corresponding behavior.

---

### Task 1: Initialize the skill scaffold and lock the public interface

**Files:**

- Create: `/Users/sunye/.codex/skills/publishing-chirpy-blog/SKILL.md`
- Create: `/Users/sunye/.codex/skills/publishing-chirpy-blog/agents/openai.yaml`
- Create: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/prepare_post.py`
- Create: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py`

- [ ] **Step 1: Confirm the target does not already exist**

Run:

```bash
test ! -e /Users/sunye/.codex/skills/publishing-chirpy-blog
```

Expected: exit code `0`. If it exists, inspect it and stop before overwriting any user-owned skill.

- [ ] **Step 2: Initialize with the official skill scaffold**

This writes outside the blog workspace and therefore requires filesystem approval.

Run:

```bash
python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  publishing-chirpy-blog \
  --path /Users/sunye/.codex/skills \
  --resources scripts \
  --interface display_name="Publish Chirpy Blog" \
  --interface short_description="Prepare and locally preview Chirpy blog posts" \
  --interface default_prompt="Use \$publishing-chirpy-blog to prepare this Markdown article and preview it locally."
```

Expected: the skill directory, `SKILL.md`, `agents/openai.yaml`, and `scripts/` are created.

- [ ] **Step 3: Add the executable and test placeholders**

Replace the generated example script with:

```python
#!/usr/bin/env python3
"""Prepare a Markdown article as a Chirpy post."""

from __future__ import annotations
```

Create `scripts/test_prepare_post.py` with:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("prepare_post.py")
SPEC = importlib.util.spec_from_file_location("prepare_post", SCRIPT)
assert SPEC and SPEC.loader
prepare_post = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_post
SPEC.loader.exec_module(prepare_post)
```

- [ ] **Step 4: Verify the scaffold and interface metadata**

Run:

```bash
sed -n '1,160p' /Users/sunye/.codex/skills/publishing-chirpy-blog/agents/openai.yaml
python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/sunye/.codex/skills/publishing-chirpy-blog
```

Expected: `openai.yaml` contains the three interface values above. Early validation may fail because `SKILL.md` is still the generated template; record the failure and continue to Task 4.

### Task 2: Build deterministic Front Matter parsing and validation with TDD

**Files:**

- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py`
- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/prepare_post.py`

- [ ] **Step 1: Write failing unit tests for parsing, normalization, and body preservation**

Append a `unittest.TestCase` that asserts:

```python
import unittest


class MetadataTests(unittest.TestCase):
    def test_body_without_front_matter_is_unchanged(self):
        metadata, body = prepare_post.split_front_matter("# 标题\n\n正文。\n")
        self.assertEqual({}, metadata)
        self.assertEqual("# 标题\n\n正文。\n", body)

    def test_existing_front_matter_is_parsed(self):
        source = '---\ntitle: "原题"\ntags: [Jekyll, macOS]\n---\n# 正文\n'
        metadata, body = prepare_post.split_front_matter(source)
        self.assertEqual("原题", metadata["title"])
        self.assertEqual(["Jekyll", "macOS"], metadata["tags"])
        self.assertEqual("# 正文\n", body)

    def test_unclosed_front_matter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unclosed Front Matter"):
            prepare_post.split_front_matter("---\ntitle: broken\n# body\n")

    def test_slug_and_tags_are_normalized(self):
        self.assertEqual("jekyll-chirpy-macos", prepare_post.normalize_slug("Jekyll_Chirpy macOS"))
        self.assertEqual(
            ["jekyll", "macos", "github-pages"],
            prepare_post.normalize_tags(["Jekyll", "macOS", "jekyll", "GitHub Pages"]),
        )

    def test_non_ascii_slug_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ASCII kebab-case"):
            prepare_post.normalize_slug("博客搭建")
```

Run:

```bash
python3 -m unittest -v \
  /Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py
```

Expected: failures or errors for missing functions.

- [ ] **Step 2: Implement the smallest parsing and normalization layer**

Implement these public functions in `prepare_post.py`: `split_front_matter(source: str)`,
`normalize_slug(value: str)`, `normalize_tags(values: list[str])`,
`parse_list(value: str)`, and `yaml_scalar(value: str)`.

Implementation rules:

- Detect Front Matter only when the first line is exactly `---`.
- Require a closing `---` line and remove only the Front Matter block.
- Parse required scalar fields and bracket lists without third-party dependencies.
- Decode quoted strings with JSON-compatible escaping.
- Reject multiline YAML constructs and malformed required fields with a precise error.
- Convert English tag whitespace/underscores to `-`, lowercase tags, and deduplicate case-insensitively.
- Require slugs to match `^[a-z0-9]+(?:-[a-z0-9]+)*$` after normalization.

- [ ] **Step 3: Run the parser tests**

Run the unit-test command from Step 1.

Expected: all five tests pass.

### Task 3: Implement repository safety and atomic post generation with TDD

**Files:**

- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py`
- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/prepare_post.py`

- [ ] **Step 1: Add temporary-repository fixtures and failing safety tests**

Add helpers that create a temporary Git repository containing `_config.yml`,
`Gemfile`, `_posts/`, and `tools/run.sh`, configure a local test identity, and
commit the fixture on `main`. Add tests named
`test_non_main_branch_is_rejected_before_write`,
`test_missing_chirpy_files_are_rejected`,
`test_duplicate_destination_is_not_overwritten`,
`test_generated_post_preserves_body_exactly`,
`test_existing_explicit_metadata_wins`, and
`test_json_receipt_contains_destination_permalink_and_metadata`.

The happy-path fixture must call the script with metadata equivalent to:

```text
--title macOS 上搭建 Jekyll Chirpy 技术博客
--categories 博客,建站
--tags jekyll,chirpy,macos,ruby,github-pages
--description 在 macOS 环境中完成 Jekyll、Chirpy 与 GitHub Pages 技术博客搭建，并记录依赖安装、构建验证和本地预览流程。
--slug jekyll-chirpy-macos
--date "2026-07-22 10:00:00 +0800"
```

Run the full unit suite.

Expected: the new tests fail because repository and write behavior do not exist.

- [ ] **Step 2: Implement the command-line contract**

Add `build_parser()`, `current_branch(repo: Path)`,
`validate_repo(repo: Path, allowed_branch: str)`,
`merge_metadata(existing: dict[str, object], supplied: dict[str, object])`,
`render_post(metadata: dict[str, object], body: str)`,
`prepare_post(args: argparse.Namespace)`, and `main()`.

Use this exact CLI:

```text
--repo PATH
--input PATH
--title TEXT
--categories CSV
--tags CSV
--description TEXT
--slug ASCII-KEBAB-CASE
--date "YYYY-MM-DD HH:MM:SS +0800"
--branch main
```

Implementation rules:

- Resolve `--repo` and `--input`; require a non-empty regular input file.
- Validate `_config.yml`, `Gemfile`, `_posts/`, and `tools/run.sh` before writing.
- Read the branch with `git -C <repo> branch --show-current`; reject anything other than the allowed branch before deriving or writing the destination.
- Validate the date strictly and use its date component in `_posts/YYYY-MM-DD-<slug>.md`.
- Preserve explicit existing required metadata; fill only missing fields from CLI values.
- Emit required keys in order: `title`, `date`, `categories`, `tags`, `description`; append preserved unknown simple keys afterward.
- Quote scalar strings with `json.dumps(value, ensure_ascii=False)`.
- Resolve the destination and prove it remains beneath `<repo>/_posts`.
- If the destination exists with different bytes, fail without changing it; if bytes are identical, return an idempotent receipt.
- For a new post, write a temporary file in `_posts`, flush and `os.fsync`, then replace atomically.
- Print only one JSON object on stdout with `source`, `destination`, `permalink`, `metadata`, and `created`.
- Return nonzero and print concise diagnostics on stderr for validation failures.

- [ ] **Step 3: Run the full script tests**

Run:

```bash
python3 -m unittest -v \
  /Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py
```

Expected: all tests pass, including explicit assertions that no destination is written on a non-`main` branch and duplicates remain unchanged.

### Task 4: Write the operational skill instructions

**Files:**

- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/SKILL.md`
- Modify: `/Users/sunye/.codex/skills/publishing-chirpy-blog/agents/openai.yaml`

- [ ] **Step 1: Replace the generated `SKILL.md` with the confirmed workflow**

Use only `name` and `description` in YAML Front Matter:

```yaml
---
name: publishing-chirpy-blog
description: Use when preparing a complete Markdown article for a Jekyll Chirpy blog, including Front Matter inference, safe post creation, build validation, and local preview without committing or pushing.
---
```

The body must stay concise and contain these imperative sections:

1. **Inputs and scope** — accept one complete Markdown file and locate the Chirpy repository.
2. **Git boundary** — inspect branch/status; default to `main`; stop on another branch unless explicitly requested; never create a branch/worktree/stash or commit/push.
3. **Infer metadata** — first H1 title fallback, 1–2 broad Chinese categories, 3–6 lowercase kebab-case tags, 60–120 Chinese-character factual description, stable ASCII slug.
4. **Taxonomy example** — for the confirmed article infer `categories: [博客, 建站]` and tags containing `jekyll`, `chirpy`, `macos`, `ruby`, `github-pages`.
5. **Prepare** — invoke `scripts/prepare_post.py` with all values and parse its JSON receipt.
6. **Validate** — run `bundle check`, then `bash tools/test.sh`; do not install missing dependencies without authorization; verify `_site/posts/<slug>/index.html` exists.
7. **Preview** — start `bash tools/run.sh`, report `http://127.0.0.1:4000/posts/<slug>/`; if port 4000 is occupied, report it and offer a different port.
8. **Stop condition** — report generated file, metadata, validation, preview URL, and pre-existing dirt; explicitly leave commit/push to the user.

- [ ] **Step 2: Normalize `agents/openai.yaml`**

Ensure it is exactly:

```yaml
interface:
  display_name: "Publish Chirpy Blog"
  short_description: "Prepare and locally preview Chirpy blog posts"
  default_prompt: "Use $publishing-chirpy-blog to prepare this Markdown article and preview it locally."
```

- [ ] **Step 3: Validate skill structure and wording**

Run:

```bash
python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/sunye/.codex/skills/publishing-chirpy-blog
rg -n "git (switch|checkout|worktree|stash|add|commit|push)|stop|main|bundle check|tools/test.sh|tools/run.sh" \
  /Users/sunye/.codex/skills/publishing-chirpy-blog/SKILL.md
```

Expected: validation succeeds; the wording scan shows the prohibitions, `main` rule, validation commands, preview command, and stop condition.

### Task 5: Forward-test against a disposable blog copy

**Files:**

- Read: `/Users/sunye/develop/code_repository/github_blog/公众号文章-macOS搭建Jekyll-Chirpy实录.md`
- Test only in: a new directory created with `mktemp -d`
- Do not modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/_posts/`

- [ ] **Step 1: Create a disposable local clone**

Run:

```bash
preview_test_dir="$(mktemp -d)"
git clone --no-hardlinks \
  /Users/sunye/develop/code_repository/github_blog/sunye423.github.io \
  "$preview_test_dir/sunye423.github.io"
test "$(git -C "$preview_test_dir/sunye423.github.io" branch --show-current)" = main
```

Expected: a clean local `main` clone. Retain `preview_test_dir` in the same
shell session for the inspection commands.

- [ ] **Step 2: Invoke the installed skill in a fresh agent context**

Give the fresh agent only the input Markdown path, disposable repository path, and the instruction to use `$publishing-chirpy-blog` and stop at preview. The forward test must verify that the agent:

- infers `categories` containing `博客`;
- infers tags containing `jekyll` and `macos`;
- creates exactly one `_posts/YYYY-MM-DD-*.md` file;
- remains on `main`;
- runs or correctly proposes `bundle check`, `bash tools/test.sh`, and `bash tools/run.sh`;
- makes no commit and performs no push.

- [ ] **Step 3: Inspect the result independently**

Run with the exact temporary path:

```bash
git -C "$preview_test_dir/sunye423.github.io" branch --show-current
git -C "$preview_test_dir/sunye423.github.io" status --short
git -C "$preview_test_dir/sunye423.github.io" log -1 --format=%H
find "$preview_test_dir/sunye423.github.io/_posts" -maxdepth 1 -type f -name '*.md' -newer "$preview_test_dir/sunye423.github.io/.git/index" -print
```

Expected: branch `main`; one untracked post; unchanged HEAD; Front Matter contains the accepted category/tag concepts; article body matches the source body.

- [ ] **Step 4: Run deterministic verification one final time**

Run:

```bash
python3 -m unittest -v \
  /Users/sunye/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py
python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/sunye/.codex/skills/publishing-chirpy-blog
```

Expected: all unit tests pass and skill validation reports success.

### Task 6: Hand off without publishing Git history

**Files:**

- Inspect: `/Users/sunye/.codex/skills/publishing-chirpy-blog/`
- Inspect: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/`

- [ ] **Step 1: Scan for unfinished content**

Run:

```bash
rg -n "TODO|TBD|PLACEHOLDER|NotImplementedError|example.py" \
  /Users/sunye/.codex/skills/publishing-chirpy-blog
```

Expected: no matches.

- [ ] **Step 2: Confirm the real blog was not modified by the forward test**

Run:

```bash
git -C /Users/sunye/develop/code_repository/github_blog/sunye423.github.io status --short --branch
```

Expected: only the already-approved documentation commits/files are present; no new `_posts/` file from skill testing.

- [ ] **Step 3: Report completion**

Report the installed skill path, test count/result, validation result, forward-test metadata, and the explicit guarantee that no article commit or push was performed. Do not commit or push the skill or blog unless the user separately requests it.
