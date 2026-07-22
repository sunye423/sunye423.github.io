# Chirpy Duplicate Title Prevention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove one redundant leading Markdown H1 from a generated Chirpy post when its visible text equals the effective Front Matter title, without changing the source article.

**Architecture:** Add a pure body transformation to `prepare_post.py` and call it only after explicit and inferred Front Matter have been merged. The transformation uses line-preserving parsing so non-matching bodies remain byte-for-byte identical and all bytes after a removed heading boundary are retained. Document the exception in the skill, synchronize the installed and repository copies, then repair and verify the existing untracked post.

**Tech Stack:** Python 3 standard library, `unittest`, Jekyll/Chirpy, Bundler, shell verification commands

## Global Constraints

- Ignore a UTF-8 BOM and blank lines only while locating a possible first body element.
- Recognize only an ATX H1 with exactly one `#` plus whitespace, or a Setext H1 with an `=` underline.
- Compare non-empty normalized visible text after trimming, whitespace collapsing, optional closing ATX marker removal, and common inline Markdown presentation removal.
- Remove at most one blank line immediately following a matching heading.
- Preserve every byte after the removed heading boundary and preserve the entire body when the leading heading does not match.
- Never modify `/Users/sunye/develop/code_repository/github_blog/公众号文章-macOS搭建Jekyll-Chirpy实录.md`.
- Keep `/Users/sunye/.codex/skills/publishing-chirpy-blog` and `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog` identical.
- Preserve all existing safe-path, no-clobber, request-file, Git-boundary, Front Matter, and permalink behavior.
- Do not commit or push the article or skill changes.

---

### Task 1: Heading normalization and removal

**Files:**
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py`
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog/scripts/prepare_post.py`

**Interfaces:**
- Consumes: Markdown body `str` and effective Front Matter title `str`.
- Produces: `normalize_heading_text(value: str) -> str` and `strip_duplicate_leading_h1(body: str, title: str) -> str`.

- [ ] **Step 1: Add focused failing unit tests**

Add this class before `RepositoryPreparationTests`:

```python
class DuplicateHeadingTests(unittest.TestCase):
    TITLE = "macOS 上搭建 Jekyll + Chirpy 技术博客"

    def test_matching_atx_h1_and_one_following_blank_line_are_removed(self):
        body = "\ufeff\r\n# macOS 上搭建 Jekyll + Chirpy 技术博客 ###\r\n\r\n正文  \r\n"
        self.assertEqual(
            "正文  \r\n",
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_matching_setext_h1_is_removed(self):
        body = "\nmacOS 上搭建 Jekyll + Chirpy 技术博客\n=====\n\n正文\n"
        self.assertEqual(
            "正文\n",
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_markdown_formatted_visible_title_matches(self):
        body = "# **macOS** 上搭建 [`Jekyll`](https://jekyllrb.com) + ~~Chirpy~~ 技术博客\n\n正文\n"
        self.assertEqual(
            "正文\n",
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_different_leading_h1_is_preserved_exactly(self):
        body = "\r\n# 不同标题\r\n\r\n正文  \r\n"
        self.assertEqual(
            body,
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_matching_h1_after_content_is_preserved_exactly(self):
        body = "引言\n\n# macOS 上搭建 Jekyll + Chirpy 技术博客\n"
        self.assertEqual(
            body,
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_body_without_h1_is_preserved_exactly(self):
        body = "\ufeff\n普通正文\n\n结尾  \n"
        self.assertEqual(
            body,
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )

    def test_only_one_following_blank_line_is_removed(self):
        body = "# macOS 上搭建 Jekyll + Chirpy 技术博客\n\n\n正文\n"
        self.assertEqual(
            "\n正文\n",
            prepare_post.strip_duplicate_leading_h1(body, self.TITLE),
        )
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run:

```bash
cd /Users/sunye/develop/code_repository/github_blog/sunye423.github.io
python3 .codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py DuplicateHeadingTests -v
```

Expected: all seven tests error with `AttributeError: module 'prepare_post' has no attribute 'strip_duplicate_leading_h1'`.

- [ ] **Step 3: Implement the minimal line-preserving transformation**

Add `import html` and `import re` if absent, then place the following functions before `render_post`:

```python
def normalize_heading_text(value: str) -> str:
    """Return comparable visible text for a Markdown heading or title."""
    normalized = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    normalized = re.sub(r"(`+)(.*?)\1", r"\2", normalized)
    normalized = re.sub(r"(?:\*\*|__|~~|\*|_)", "", normalized)
    normalized = re.sub(r"\\([\\`*{}\[\]()#+.!_>-])", r"\1", normalized)
    return " ".join(html.unescape(normalized).split())


def strip_duplicate_leading_h1(body: str, title: str) -> str:
    """Remove one leading H1 only when its visible text equals title."""
    lines = body.splitlines(keepends=True)
    first = 0
    while first < len(lines):
        visible = lines[first]
        if first == 0:
            visible = visible.removeprefix("\ufeff")
        if visible.strip(" \t\r\n"):
            break
        first += 1
    if first == len(lines):
        return body

    line = lines[first]
    candidate_line = line.removeprefix("\ufeff") if first == 0 else line
    candidate = ""
    end = first
    atx = re.match(r"^[ \t]*#(?!#)[ \t]+(.*?)[\r\n]*$", candidate_line)
    if atx:
        candidate = re.sub(r"[ \t]+#+[ \t]*$", "", atx.group(1))
    elif first + 1 < len(lines) and re.match(
        r"^[ \t]*=+[ \t]*(?:\r?\n)?$", lines[first + 1]
    ):
        candidate = candidate_line.rstrip("\r\n")
        end = first + 1
    else:
        return body

    if not candidate or normalize_heading_text(candidate) != normalize_heading_text(title):
        return body

    after = end + 1
    if after < len(lines) and not lines[after].strip(" \t\r\n"):
        after += 1
    return "".join(lines[after:])
```

- [ ] **Step 4: Run the focused tests and observe GREEN**

Run the command from Step 2.

Expected: `Ran 7 tests` and `OK`.

- [ ] **Step 5: Run the complete helper suite**

Run:

```bash
python3 sunye423.github.io/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py
```

Expected: the original 39 tests plus the seven new tests pass with `OK`.

### Task 2: Integrate the rule and document the skill

**Files:**
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py`
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog/scripts/prepare_post.py`
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog/SKILL.md`
- Synchronize: `/Users/sunye/.codex/skills/publishing-chirpy-blog/`

**Interfaces:**
- Consumes: `strip_duplicate_leading_h1(body: str, title: str)` from Task 1 and merged `metadata["title"]`.
- Produces: generated posts without a matching leading H1 and two byte-identical skill directories.

- [ ] **Step 1: Add failing integration and source-integrity tests**

Add these methods to `RepositoryPreparationTests`:

```python
    def test_generated_post_removes_h1_matching_effective_title(self):
        body = f"# {self.TITLE}\n\n正文末尾  \n"
        source_bytes = body.encode("utf-8")
        self.input.write_bytes(source_bytes)
        before = self.input.read_bytes()

        result = self._run(input_text=body)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.input.read_bytes())
        with self.destination.open("r", encoding="utf-8", newline="") as stream:
            _, generated_body = prepare_post.split_front_matter(stream.read())
        self.assertEqual("正文末尾  \n", generated_body)

    def test_skill_documents_duplicate_title_exception(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("leading H1", text)
        self.assertIn("effective Front Matter title", text)
        self.assertIn("source file unchanged", text)
```

Also add this class after `RepositoryPreparationTests`:

```python
class SkillSynchronizationTests(unittest.TestCase):
    def test_installed_and_repository_skill_files_are_identical(self):
        installed = Path("/Users/sunye/.codex/skills/publishing-chirpy-blog")
        repository = SCRIPT.parents[1]
        relative_files = (
            Path("SKILL.md"),
            Path("agents/openai.yaml"),
            Path("scripts/prepare_post.py"),
            Path("scripts/test_prepare_post.py"),
        )
        for relative_file in relative_files:
            with self.subTest(relative_file=str(relative_file)):
                self.assertEqual(
                    (repository / relative_file).read_bytes(),
                    (installed / relative_file).read_bytes(),
                )
```

- [ ] **Step 2: Run the two new tests and observe RED**

Run:

```bash
cd /Users/sunye/develop/code_repository/github_blog/sunye423.github.io
python3 .codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py \
  RepositoryPreparationTests.test_generated_post_removes_h1_matching_effective_title \
  RepositoryPreparationTests.test_skill_documents_duplicate_title_exception \
  SkillSynchronizationTests -v
```

Expected: the generated body still contains the H1, `SKILL.md` lacks the required rule wording, and the two skill copies differ once the repository tests have been added.

- [ ] **Step 3: Integrate the transformer after metadata merge**

Change the `prepare_post` rendering sequence to:

```python
    metadata = merge_metadata(existing, supplied)
    effective_date = _validate_required_metadata(metadata, set(existing))
    effective_slug = _effective_slug(metadata, publication_slug)
    permalink = _effective_permalink(metadata, effective_slug)
    generated_body = strip_duplicate_leading_h1(body, str(metadata["title"]))
    rendered = render_post(metadata, generated_body)
```

Update `render_post`'s docstring to `Render supported Front Matter followed by the prepared Markdown body.`

- [ ] **Step 4: Replace the unconditional body-preservation wording**

In `SKILL.md`, change the metadata paragraph ending to:

```markdown
Infer missing values semantically from the complete article while preserving every explicit source Front Matter value. Keep the source file unchanged. In the generated Chirpy post only, remove one leading H1 when its normalized visible text equals the effective Front Matter title; otherwise preserve the Markdown body exactly:
```

Change the preparation receipt check to:

```markdown
Confirm the source file unchanged. Confirm that the generated Markdown body matches it exactly except for one removed leading H1, plus at most one immediately following blank line, when that heading duplicates the effective Front Matter title.
```

- [ ] **Step 5: Run the integration tests and retain the synchronization RED test**

Run:

```bash
cd /Users/sunye/develop/code_repository/github_blog/sunye423.github.io
python3 .codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py \
  RepositoryPreparationTests.test_generated_post_removes_h1_matching_effective_title \
  RepositoryPreparationTests.test_skill_documents_duplicate_title_exception \
  SkillSynchronizationTests -v
```

Expected: both behavior/documentation tests pass; only `SkillSynchronizationTests` remains red because the installed copy has not yet been synchronized.

- [ ] **Step 6: Synchronize and verify the two skill copies**

Copy the three changed files from the repository skill to the same relative paths under `/Users/sunye/.codex/skills/publishing-chirpy-blog`, then run:

```bash
diff -ru /Users/sunye/.codex/skills/publishing-chirpy-blog /Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog
PYTHONPATH=/private/tmp/publishing-chirpy-blog-validator-deps python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/sunye/.codex/skills/publishing-chirpy-blog
PYTHONPATH=/private/tmp/publishing-chirpy-blog-validator-deps python3 /Users/sunye/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/sunye/develop/code_repository/github_blog/sunye423.github.io/.codex/skills/publishing-chirpy-blog
```

Expected: `diff` prints nothing and both validators print `Skill is valid!`.

- [ ] **Step 7: Run the complete synchronized helper suite**

Run:

```bash
cd /Users/sunye/develop/code_repository/github_blog/sunye423.github.io
python3 .codex/skills/publishing-chirpy-blog/scripts/test_prepare_post.py
```

Expected: all 49 tests pass with `OK`.

### Task 3: Repair and verify the current article preview

**Files:**
- Modify: `/Users/sunye/develop/code_repository/github_blog/sunye423.github.io/_posts/2026-07-22-build-jekyll-chirpy-blog-on-macos.md`
- Verify unchanged: `/Users/sunye/develop/code_repository/github_blog/公众号文章-macOS搭建Jekyll-Chirpy实录.md`

**Interfaces:**
- Consumes: the duplicate-title rule implemented and validated in Tasks 1–2.
- Produces: one locally previewable Chirpy post with a single rendered article H1.

- [ ] **Step 1: Record the source hash and inspect the generated heading boundary**

Run:

```bash
shasum -a 256 /Users/sunye/develop/code_repository/github_blog/公众号文章-macOS搭建Jekyll-Chirpy实录.md
sed -n '1,20p' /Users/sunye/develop/code_repository/github_blog/sunye423.github.io/_posts/2026-07-22-build-jekyll-chirpy-blog-on-macos.md
```

Expected source hash: `23e645fc4a58e88991b3b22ca38c5e064dd44d83d15a3b6d6d0f4e2d8d019e28`; the post contains a Front Matter title followed by the same body H1.

- [ ] **Step 2: Remove only the duplicate body H1 and one following blank line**

Apply this exact conceptual edit, retaining all Front Matter and later body bytes:

```diff
-# macOS 上搭建 Jekyll + Chirpy 技术博客：环境配置与问题排查
-
 GitHub Pages、Jekyll、Chirpy 与 GitHub Actions 可以组成一套轻量的静态博客方案：Markdown 负责内容，Jekyll 生成页面，Chirpy 提供主题，GitHub Pages 与 Actions 完成托管和自动部署。
```

- [ ] **Step 3: Verify source integrity and production build**

Run from the Chirpy repository:

```bash
shasum -a 256 /Users/sunye/develop/code_repository/github_blog/公众号文章-macOS搭建Jekyll-Chirpy实录.md
bundle check
bash tools/test.sh
test -f _site/posts/build-jekyll-chirpy-blog-on-macos/index.html
```

Expected: the hash remains `23e645fc4a58e88991b3b22ca38c5e064dd44d83d15a3b6d6d0f4e2d8d019e28`; Bundler reports dependencies satisfied; the Jekyll/HTML-Proofer command exits 0; the artifact exists.

- [ ] **Step 4: Verify a single article H1 and HTTP preview**

Run:

```bash
rg -o '<h1\b' _site/posts/build-jekyll-chirpy-blog-on-macos/index.html | wc -l
curl --fail --silent --output /dev/null http://127.0.0.1:4000/posts/build-jekyll-chirpy-blog-on-macos/
```

Expected: the H1 count is `1` and `curl` exits 0. If the existing LiveReload process has stopped, restart `bash tools/run.sh` on port 4000 before retrying the HTTP check.

- [ ] **Step 5: Confirm the intended uncommitted scope**

Run:

```bash
git status --short --branch
git diff -- .codex/skills/publishing-chirpy-blog _posts/2026-07-22-build-jekyll-chirpy-blog-on-macos.md
```

Expected: branch `main` remains ahead only by the already committed design document; the skill files and article remain local changes; no new branch, worktree, stash, commit, or push has been created.
