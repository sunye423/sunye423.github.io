from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("prepare_post.py")
SKILL = SCRIPT.parents[1] / "SKILL.md"
SPEC = importlib.util.spec_from_file_location("prepare_post", SCRIPT)
assert SPEC and SPEC.loader
prepare_post = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_post
SPEC.loader.exec_module(prepare_post)


import unittest
from unittest import mock


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

    def test_non_kebab_english_tags_are_rejected(self):
        for value in ["C++", "hello!", "foo--bar"]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "kebab-case"):
                    prepare_post.normalize_tags([value])

    def test_concise_chinese_tag_is_preserved(self):
        self.assertEqual(["博客搭建"], prepare_post.normalize_tags(["博客搭建"]))

    def test_malformed_and_multiline_lists_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed YAML list"):
            prepare_post.parse_list("[one,]")
        with self.assertRaisesRegex(ValueError, "multiline YAML"):
            prepare_post.parse_list("[one,\ntwo]")

    def test_extended_numeric_scalars_preserve_semantics(self):
        source = (
            "---\n"
            "leading: .5\n"
            "trailing: 1.\n"
            "positive: +2\n"
            "negative: -.5\n"
            "exponent: +1.25e+2\n"
            "---\n"
        )
        expected = {
            "leading": 0.5,
            "trailing": 1.0,
            "positive": 2,
            "negative": -0.5,
            "exponent": 125.0,
        }

        metadata, body = prepare_post.split_front_matter(source)
        rendered = prepare_post.render_post(metadata, body)
        reparsed, _ = prepare_post.split_front_matter(rendered)

        self.assertEqual(expected, metadata)
        self.assertEqual(expected, reparsed)

    def test_unsupported_numeric_spelling_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "numeric"):
            prepare_post.yaml_scalar("0x10")


class RepositoryPreparationTests(unittest.TestCase):
    TITLE = "macOS 上搭建 Jekyll Chirpy 技术博客"
    CATEGORIES = "博客,建站"
    TAGS = "jekyll,chirpy,macos,ruby,github-pages"
    DESCRIPTION = (
        "在 macOS 环境中完成 Jekyll、Chirpy 与 GitHub Pages 技术博客搭建，"
        "并记录依赖安装、构建验证和本地预览流程。"
    )
    SLUG = "jekyll-chirpy-macos"
    DATE = "2026-07-22 10:00:00 +0800"

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "site"
        self.input = self.root / "article.md"
        self._create_repo()

    def _create_repo(self):
        self.repo.mkdir()
        (self.repo / "_config.yml").write_text("theme: jekyll-theme-chirpy\n", encoding="utf-8")
        (self.repo / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
        (self.repo / "_posts").mkdir()
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Test Author")
        self._git("config", "user.email", "test@example.com")
        self._git("add", ".")
        self._git("commit", "-m", "fixture")

    def _git(self, *arguments):
        subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _run(self, *, input_text="# 标题\n\n正文。\n", extra_arguments=()):
        with self.input.open("w", encoding="utf-8", newline="") as stream:
            stream.write(input_text)
        command = [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(self.repo),
            "--input",
            str(self.input),
            "--title",
            self.TITLE,
            "--categories",
            self.CATEGORIES,
            "--tags",
            self.TAGS,
            "--description",
            self.DESCRIPTION,
            "--slug",
            self.SLUG,
            "--date",
            self.DATE,
            "--branch",
            "main",
            *extra_arguments,
        ]
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _request_payload(self, **overrides):
        payload = {
            "repo": str(self.repo),
            "input": str(self.input),
            "title": self.TITLE,
            "categories": ["博客", "建站"],
            "tags": ["jekyll", "chirpy", "macos", "ruby", "github-pages"],
            "description": self.DESCRIPTION,
            "slug": self.SLUG,
            "date": self.DATE,
            "branch": "main",
        }
        payload.update(overrides)
        return payload

    def _run_request(
        self, payload, *, input_text="# 标题\n\n正文。\n", consume=False
    ):
        input_path = Path(payload["input"])
        input_path.parent.mkdir(parents=True, exist_ok=True)
        with input_path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(input_text)
        descriptor, request_name = tempfile.mkstemp(
            dir=self.root, prefix="request-", suffix=".json"
        )
        os.close(descriptor)
        self.request_path = Path(request_name)
        self.assertEqual(0o600, stat.S_IMODE(self.request_path.stat().st_mode))
        self.request_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        command = [
            sys.executable,
            str(SCRIPT),
            "--request",
            str(self.request_path),
        ]
        if consume:
            command.append("--consume-request")
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @property
    def destination(self):
        return self.repo / "_posts" / "2026-07-22-jekyll-chirpy-macos.md"

    def test_non_main_branch_is_rejected_before_write(self):
        self._git("switch", "-c", "feature")

        result = self._run()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("branch", result.stderr.lower())
        self.assertEqual("", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_missing_chirpy_files_are_rejected(self):
        required_paths = ["_config.yml", "Gemfile", "_posts", "tools/run.sh"]
        for missing_path in required_paths:
            with self.subTest(missing_path=missing_path):
                try:
                    if missing_path == "_posts":
                        (self.repo / missing_path).rmdir()
                    else:
                        (self.repo / missing_path).unlink()

                    result = self._run()

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(missing_path, result.stderr)
                    self.assertEqual("", result.stdout)
                finally:
                    if missing_path == "_posts":
                        (self.repo / missing_path).mkdir(exist_ok=True)
                    else:
                        path = self.repo / missing_path
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("fixture\n", encoding="utf-8")

    def test_symlinked_posts_directory_is_rejected(self):
        posts = self.repo / "_posts"
        posts.rmdir()
        outside_posts = self.root / "outside-posts"
        outside_posts.mkdir()
        posts.symlink_to(outside_posts, target_is_directory=True)

        result = self._run()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("_posts", result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual([], list(outside_posts.iterdir()))

    def test_duplicate_destination_is_not_overwritten(self):
        original = b"existing post must remain unchanged\n"
        self.destination.write_bytes(original)

        result = self._run()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("destination", result.stderr.lower())
        self.assertEqual("", result.stdout)
        self.assertEqual(original, self.destination.read_bytes())

    def test_generated_post_preserves_body_exactly(self):
        body = "\r\n# 正文\r\n\r\nLine with trailing spaces.  \r\n"
        source = '---\ntitle: "已有标题"\n---\n' + body

        result = self._run(input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(self.destination.exists(), "the generated destination is missing")
        with self.destination.open("r", encoding="utf-8", newline="") as stream:
            _, generated_body = prepare_post.split_front_matter(stream.read())
        self.assertEqual(body, generated_body)

    def test_existing_explicit_metadata_wins(self):
        existing = {
            "title": "已有标题",
            "date": "2025-01-02 03:04:05 +0800",
            "categories": ["已有分类"],
            "tags": ["已有标签"],
            "description": "已有描述",
        }
        source = (
            "---\n"
            'title: "已有标题"\n'
            'date: "2025-01-02 03:04:05 +0800"\n'
            'categories: ["已有分类"]\n'
            'tags: ["已有标签"]\n'
            'description: "已有描述"\n'
            "pin: false\n"
            "---\n"
            "正文\n"
        )

        result = self._run(input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        existing_destination = self.repo / "_posts" / "2025-01-02-jekyll-chirpy-macos.md"
        self.assertTrue(existing_destination.exists(), "the generated destination is missing")
        with existing_destination.open("r", encoding="utf-8", newline="") as stream:
            rendered = stream.read()
        metadata, _ = prepare_post.split_front_matter(rendered)
        self.assertEqual(existing, {key: metadata[key] for key in existing})
        self.assertIs(False, metadata["pin"])
        field_lines = rendered.splitlines()[1:7]
        self.assertEqual(
            ["title", "date", "categories", "tags", "description", "pin"],
            [line.split(":", 1)[0] for line in field_lines],
        )

    def test_existing_explicit_category_and_tag_values_are_preserved(self):
        source = (
            "---\n"
            'categories: [" Existing Category "]\n'
            'tags: ["Jekyll", "GitHub Pages"]\n'
            "---\n"
            "正文\n"
        )
        expected_categories = [" Existing Category "]
        expected_tags = ["Jekyll", "GitHub Pages"]

        result = self._run(input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(expected_categories, receipt["metadata"]["categories"])
        self.assertEqual(expected_tags, receipt["metadata"]["tags"])
        rendered = self.destination.read_text(encoding="utf-8")
        self.assertIn('categories: [" Existing Category "]', rendered)
        self.assertIn('tags: ["Jekyll", "GitHub Pages"]', rendered)

    def test_json_receipt_contains_destination_permalink_and_metadata(self):
        result = self._run()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertNotEqual("", result.stdout, "the JSON receipt is missing")
        receipt = json.loads(result.stdout)
        self.assertEqual(
            {"source", "destination", "permalink", "metadata", "created"},
            set(receipt),
        )
        self.assertEqual(str(self.input.resolve()), receipt["source"])
        self.assertEqual(str(self.destination.resolve()), receipt["destination"])
        self.assertEqual("/posts/jekyll-chirpy-macos/", receipt["permalink"])
        self.assertEqual(self.TITLE, receipt["metadata"]["title"])
        self.assertEqual(["博客", "建站"], receipt["metadata"]["categories"])
        self.assertEqual(["jekyll", "chirpy", "macos", "ruby", "github-pages"], receipt["metadata"]["tags"])
        self.assertTrue(receipt["created"])
        self.assertEqual(1, len(result.stdout.splitlines()))

        repeated = self._run()
        self.assertEqual(0, repeated.returncode, repeated.stderr)
        self.assertFalse(json.loads(repeated.stdout)["created"])

    def test_request_file_preserves_untrusted_values_without_execution(self):
        marker = self.root / "interpolated-marker"
        hostile_input = (
            self.root
            / f'input $(touch {marker}) `touch {marker}` ${{HOME}} "quoted"'
            / "article.md"
        )
        title = f'Quoted "title"\n$(touch {marker}) `touch {marker}` ${{HOME}}'
        categories = ["博客", f"$(touch {marker})", f"`touch {marker}`", "${HOME}"]
        description = f'Line one\n"line two" $(touch {marker}) `touch {marker}` ${{HOME}}'
        payload = self._request_payload(
            input=str(hostile_input),
            title=title,
            categories=categories,
            description=description,
        )
        source = "# 原文\n\n正文必须保持不变。  \n"

        result = self._run_request(payload, input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(marker.exists(), "article data was interpreted by a shell")
        self.assertEqual(source, hostile_input.read_text(encoding="utf-8"))
        receipt = json.loads(result.stdout)
        self.assertEqual(title, receipt["metadata"]["title"])
        self.assertEqual(categories, receipt["metadata"]["categories"])
        self.assertEqual(description, receipt["metadata"]["description"])
        rendered_metadata, _ = prepare_post.split_front_matter(
            self.destination.read_text(encoding="utf-8")
        )
        self.assertEqual(title, rendered_metadata["title"])
        self.assertEqual(categories, rendered_metadata["categories"])
        self.assertEqual(description, rendered_metadata["description"])

    def test_request_file_requires_exact_keys_and_value_types(self):
        valid = self._request_payload()
        cases = {
            "extra key": {**valid, "extra": "value"},
            "missing key": {key: value for key, value in valid.items() if key != "title"},
            "repo type": {**valid, "repo": 7},
            "categories type": {**valid, "categories": "博客,建站"},
            "categories item type": {**valid, "categories": ["博客", 7]},
            "tags type": {**valid, "tags": "jekyll"},
            "tags item type": {**valid, "tags": ["jekyll", False]},
            "branch type": {**valid, "branch": None},
        }
        for case, payload in cases.items():
            with self.subTest(case=case):
                request_path = self.root / "request.json"
                request_path.write_text(json.dumps(payload), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--request", str(request_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("request", result.stderr.lower())
                self.assertEqual("", result.stdout)
                self.assertFalse(self.destination.exists())

    def test_request_file_is_mutually_exclusive_with_legacy_flags(self):
        payload = self._request_payload()
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(payload), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--request",
                str(request_path),
                "--repo",
                str(self.repo),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("mutually exclusive", result.stderr.lower())
        self.assertEqual("", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_consume_request_deletes_only_exact_file_after_success(self):
        sentinel = self.root / "sibling-sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")

        result = self._run_request(self._request_payload(), consume=True)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.request_path.exists())
        self.assertEqual("keep\n", sentinel.read_text(encoding="utf-8"))

    def test_consume_request_deletes_only_exact_file_after_validation_failure(self):
        sentinel = self.root / "sibling-sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")
        payload = self._request_payload(branch="feature")

        result = self._run_request(payload, consume=True)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("branch", result.stderr.lower())
        self.assertFalse(self.request_path.exists())
        self.assertEqual("keep\n", sentinel.read_text(encoding="utf-8"))
        self.assertFalse(self.destination.exists())

    def test_consume_request_requires_request_mode(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--consume-request"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("--request", result.stderr)
        self.assertEqual("", result.stdout)

    def test_valid_unknown_yaml_blocks_comments_and_single_quotes_round_trip(self):
        source = (
            "---\n"
            "# leading comment\n"
            "\n"
            "title: 'Bob''s title'  # keep title context\n"
            "date: '2025-01-02 03:04:05 +0800'\n"
            "categories: ['已有分类']\n"
            "tags: ['Jekyll', 'GitHub Pages']\n"
            "description: 'It''s a factual description.'\n"
            "# unknown entries\n"
            "label: 'Bob''s notes'\n"
            "defaults: &defaults\n"
            "  layout: post\n"
            "  nested:\n"
            "    enabled: true\n"
            "features:\n"
            "  - one\n"
            "  - two\n"
            "literal: |\n"
            "  first line\n"
            "  second: line\n"
            "folded: >\n"
            "  folded\n"
            "  text\n"
            "alias: *defaults\n"
            "matrix: {a: 1}\n"
            "# trailing comment\n"
            "\n"
            "---\n"
            "正文\n"
        )
        preserved = (
            "# leading comment\n"
            "\n"
            "# unknown entries\n"
            "label: 'Bob''s notes'\n"
            "defaults: &defaults\n"
            "  layout: post\n"
            "  nested:\n"
            "    enabled: true\n"
            "features:\n"
            "  - one\n"
            "  - two\n"
            "literal: |\n"
            "  first line\n"
            "  second: line\n"
            "folded: >\n"
            "  folded\n"
            "  text\n"
            "alias: *defaults\n"
            "matrix: {a: 1}\n"
            "# trailing comment\n"
            "\n"
        )

        result = self._run(input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual("Bob's title", receipt["metadata"]["title"])
        self.assertEqual("It's a factual description.", receipt["metadata"]["description"])
        self.assertEqual("Bob's notes", receipt["metadata"]["label"])
        self.assertNotIn("defaults", receipt["metadata"])
        destination = self.repo / "_posts" / "2025-01-02-jekyll-chirpy-macos.md"
        rendered = destination.read_text(encoding="utf-8")
        expected_front_matter = (
            "---\n"
            'title: "Bob\'s title"  # keep title context\n'
            'date: "2025-01-02 03:04:05 +0800"\n'
            'categories: ["已有分类"]\n'
            'tags: ["Jekyll", "GitHub Pages"]\n'
            'description: "It\'s a factual description."\n'
            + preserved
            + "---\n"
        )
        self.assertEqual(expected_front_matter + "正文\n", rendered)

    def test_required_nested_or_block_values_are_rejected_before_write(self):
        cases = {
            "nested title": "title:\n  nested: value\n",
            "block description": "description: |\n  text\n",
            "block categories": "categories:\n  - 博客\n",
        }
        for case, required_yaml in cases.items():
            with self.subTest(case=case):
                result = self._run(input_text=f"---\n{required_yaml}---\n正文\n")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("required", result.stderr.lower())
                self.assertEqual("", result.stdout)
                self.assertFalse(self.destination.exists())

    def test_safe_custom_permalink_is_authoritative(self):
        result = self._run(
            input_text="---\npermalink: '/guides/custom-path/'\n---\n正文\n"
        )

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual("/guides/custom-path/", receipt["permalink"])
        self.assertEqual("/guides/custom-path/", receipt["metadata"]["permalink"])
        self.assertIn(
            "permalink: '/guides/custom-path/'",
            self.destination.read_text(encoding="utf-8"),
        )

    def test_unsafe_custom_permalink_is_rejected_before_write(self):
        unsafe_values = [
            "posts/relative/",
            "/missing-trailing",
            "/posts/../secret/",
            "/posts/./entry/",
            "/posts/entry/?query=1",
            "/posts/entry/#fragment",
            "/posts\\entry/",
            "/posts//entry/",
            "/posts/\x00entry/",
            "/posts/$(touch-marker)/",
            "/posts/`touch-marker`/",
            "/posts/'single-quote'/",
            '/posts/"double-quote"/',
            "/posts/line\nbreak/",
            "/posts/tab\tbreak/",
            "/posts/space break/",
            "/posts/%2f/",
            "/posts/%2e/",
            "/posts/control\x01char/",
            "/posts/semicolon;command/",
        ]
        for value in unsafe_values:
            with self.subTest(value=value):
                try:
                    source = "---\n" + f"permalink: {json.dumps(value)}\n" + "---\n正文\n"
                    result = self._run(input_text=source)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("permalink", result.stderr.lower())
                    self.assertEqual("", result.stdout)
                    self.assertFalse(self.destination.exists())
                finally:
                    self.destination.unlink(missing_ok=True)

    def test_explicit_slug_controls_default_receipt_permalink(self):
        result = self._run(
            input_text="---\nslug: 'existing-article-slug'\n---\n正文\n"
        )

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual("/posts/existing-article-slug/", receipt["permalink"])
        self.assertEqual("existing-article-slug", receipt["metadata"]["slug"])
        self.assertEqual(str(self.destination.resolve()), receipt["destination"])
        self.assertIn(
            "slug: 'existing-article-slug'",
            self.destination.read_text(encoding="utf-8"),
        )

    def test_invalid_explicit_slug_is_rejected_before_write(self):
        invalid_values = [
            "false",
            '""',
            '"Not-Kebab"',
            '"two words"',
            '"../escape"',
            '"with_underscore"',
        ]
        for rendered_value in invalid_values:
            with self.subTest(value=rendered_value):
                try:
                    source = f"---\nslug: {rendered_value}\n---\n正文\n"
                    result = self._run(input_text=source)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("slug", result.stderr.lower())
                    self.assertEqual("", result.stdout)
                    self.assertFalse(self.destination.exists())
                finally:
                    self.destination.unlink(missing_ok=True)

    def test_unknown_scalar_semantics_are_preserved(self):
        source = (
            "---\n"
            "pin: false\n"
            "order: 7\n"
            "ratio: -1.25\n"
            "published: null\n"
            "---\n"
            "正文\n"
        )

        result = self._run(input_text=source)

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        expected = {"pin": False, "order": 7, "ratio": -1.25, "published": None}
        self.assertEqual(expected, {key: receipt["metadata"][key] for key in expected})
        rendered = self.destination.read_text(encoding="utf-8")
        metadata, _ = prepare_post.split_front_matter(rendered)
        self.assertEqual(expected, {key: metadata[key] for key in expected})
        for line in ("pin: false", "order: 7", "ratio: -1.25", "published: null"):
            self.assertIn(f"\n{line}\n", rendered)

    def test_invalid_existing_required_types_and_empty_values_are_rejected(self):
        cases = {
            "title type": ("title", "title: false"),
            "title empty": ("title", 'title: ""'),
            "date type": ("date", "date: false"),
            "categories type": ("categories", "categories: category"),
            "categories empty": ("categories", "categories: []"),
            "tags type": ("tags", "tags: tag"),
            "tags empty": ("tags", "tags: []"),
            "description type": ("description", "description: null"),
            "description empty": ("description", 'description: ""'),
        }
        for case, (field, front_matter) in cases.items():
            with self.subTest(case=case):
                try:
                    result = self._run(input_text=f"---\n{front_matter}\n---\n正文\n")

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(field, result.stderr.lower())
                    self.assertEqual("", result.stdout)
                finally:
                    for post in (self.repo / "_posts").glob("*.md"):
                        post.unlink()

    def test_wrong_timezone_offset_is_rejected(self):
        result = self._run(
            extra_arguments=("--date", "2026-07-22 10:00:00 +0000")
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("+0800", result.stderr)
        self.assertEqual("", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_unsupported_unknown_structures_are_preserved_without_interpretation(self):
        result = self._run(input_text="---\nweights: [1, 2]\n---\n正文\n")

        self.assertEqual(0, result.returncode, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertNotIn("weights", receipt["metadata"])
        self.assertIn(
            "\nweights: [1, 2]\n",
            self.destination.read_text(encoding="utf-8"),
        )


class AtomicPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.destination = self.directory / "post.md"

    def temporary_files(self):
        return list(self.directory.glob(".post.md.*.tmp"))

    def test_concurrent_destination_is_never_clobbered(self):
        real_link = os.link
        concurrent_content = b"concurrent writer\n"

        def publish_after_concurrent_writer(source, destination):
            Path(destination).write_bytes(concurrent_content)
            return real_link(source, destination)

        with mock.patch.object(
            prepare_post.os, "link", side_effect=publish_after_concurrent_writer
        ):
            with self.assertRaisesRegex(ValueError, "different content"):
                prepare_post._atomic_write(self.destination, b"our content\n")

        self.assertEqual(concurrent_content, self.destination.read_bytes())
        self.assertEqual([], self.temporary_files())

    def test_temporary_file_is_cleaned_when_publication_fails(self):
        with mock.patch.object(
            prepare_post.os, "link", side_effect=OSError("publication failed")
        ):
            with self.assertRaisesRegex(OSError, "publication failed"):
                prepare_post._atomic_write(self.destination, b"content\n")

        self.assertFalse(self.destination.exists())
        self.assertEqual([], self.temporary_files())

    def test_new_post_mode_is_0644(self):
        created = prepare_post._atomic_write(self.destination, b"content\n")

        self.assertTrue(created)
        self.assertEqual(0o644, stat.S_IMODE(self.destination.stat().st_mode))


class SkillInstructionsTests(unittest.TestCase):
    def test_prepare_workflow_uses_only_a_structured_request_file(self):
        instructions = SKILL.read_text(encoding="utf-8")

        self.assertIn('request_path="$(mktemp -t publishing-chirpy-blog)"', instructions)
        self.assertIn('chmod 600 -- "$request_path"', instructions)
        self.assertIn(
            '--request "$request_path" --consume-request', instructions
        )
        self.assertIn("delete only that exact request file", instructions)
        for unsafe_fragment in (
            'title="',
            'description="',
            'categories_csv="',
            'tags_csv="',
            'skill_dir="',
            "assign every inferred value directly to a shell variable",
        ):
            self.assertNotIn(unsafe_fragment, instructions)

    def test_validation_derives_artifact_and_preview_from_receipt_permalink(self):
        instructions = SKILL.read_text(encoding="utf-8")

        self.assertIn(
            "_site/<receipt permalink without leading slash>/index.html",
            instructions,
        )
        self.assertNotIn("_site/posts/<slug>/index.html", instructions)
        self.assertIn("receipt `permalink`", instructions)
        self.assertIn(
            "Never interpolate the receipt `permalink` into a shell command",
            instructions,
        )
        self.assertIn("non-shell path API", instructions)


if __name__ == "__main__":
    unittest.main()
