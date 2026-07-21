# Publishing Chirpy Blog Skill Design

## Goal

Create a personal Codex skill named `publishing-chirpy-blog` under
`~/.codex/skills`. Given a complete Markdown article, the skill prepares a
Chirpy post in the current blog repository and starts local preview. It stops
before staging, committing, pushing, deploying, or publishing remotely.

The initial target repository is:

```text
/Users/sunye/develop/code_repository/github_blog/sunye423.github.io
```

## Confirmed behavior

- Treat `main` as the default and only permitted branch unless the user
  explicitly requests another branch.
- Do not create feature branches, linked worktrees, stashes, commits, or pushes.
- Preserve the source Markdown file.
- Create or update one file beneath `_posts/`.
- Infer title, categories, tags, description, and slug from the article.
- Validate the generated post and start the repository's existing local preview.
- Leave commit and push operations to the user.

## Baseline findings

The no-skill baseline correctly discovered the Jekyll commands but introduced
unwanted behavior:

- It interpreted “publish” as permission to commit and push.
- It proposed creating a temporary worktree when branch or working-tree state
  was inconvenient.
- It left tag capitalization and taxonomy rules ambiguous.

The skill must define these boundaries explicitly.

## Skill structure

```text
publishing-chirpy-blog/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    ├── prepare_post.py
    └── test_prepare_post.py
```

No README, assets, or separate reference document is required. Keep the
project-specific workflow and taxonomy rules concise in `SKILL.md`; keep file
generation and validation deterministic in `prepare_post.py`.

## Metadata inference

Codex performs semantic inference before invoking the script.

### Title

Use the first H1. If no H1 exists, derive a concise title from the opening
paragraph and report that inference.

### Categories

Choose one or two broad Chinese categories. Prefer categories already present
under `_posts/` when they fit the subject. Categories describe the article's
content family, not every technology mentioned.

For the accepted example:

```yaml
categories: [博客, 建站]
```

### Tags

Choose three to six specific technologies or concepts. Normalize English tags
to lowercase kebab-case and deduplicate them case-insensitively. Use concise
Chinese tags only when an established English technical name is not clearer.

For the accepted example:

```yaml
tags: [jekyll, chirpy, macos, ruby, github-pages]
```

This representation identifies the required concepts `Jekyll`, `博客`, and
`macOS` while following the repository's lowercase tag convention.

### Description

Write a factual 60–120 Chinese-character summary based on the title, opening
paragraph, and article scope. Do not add claims absent from the article.

### Slug

Generate a stable lowercase ASCII kebab-case slug from the title's subject.
Exclude source-specific prefixes such as `公众号文章-`. The destination is
`_posts/YYYY-MM-DD-<slug>.md`.

## Front Matter contract

Generate this field order:

```yaml
---
title: "<title>"
date: YYYY-MM-DD HH:MM:SS +0800
categories: [<category>, <category>]
tags: [<tag>, <tag>]
description: "<description>"
---
```

Use the current `Asia/Shanghai` time and ensure it is not in the future. Quote
string values safely. If the input already has Front Matter, preserve explicit
values and fill only missing required fields unless the user asks to replace
metadata.

Preserve the Markdown body byte-for-byte apart from removing an existing Front
Matter block from the body before writing the normalized block.

## Deterministic script interface

`prepare_post.py` accepts:

```text
--repo
--input
--title
--categories
--tags
--description
--slug
--date
```

The script:

1. Resolve and validate the repository and input paths.
2. Require the repository branch to be `main` by default.
3. Confirm `_config.yml`, `Gemfile`, `_posts/`, and `tools/run.sh` exist.
4. Reject path traversal and destinations outside `_posts/`.
5. Merge existing Front Matter according to the contract.
6. Refuse to overwrite a different existing post.
7. Write the post atomically and print a JSON receipt containing the destination,
   permalink, metadata, and source path.

The script does not perform semantic classification, install dependencies,
start Jekyll, or run Git mutations.

## Repository and Git safety

- If the current branch is not `main`, stop before writing and explain that
  another branch requires an explicit user request.
- If `main` contains unrelated changes, preserve them and continue only when
  the destination post does not overlap. Report that preview includes the whole
  working tree.
- If the destination already exists with different content, stop and ask the
  user to choose a new slug or approve replacement.
- Never run `git switch`, `git checkout`, `git worktree`, `git stash`,
  `git add`, `git commit`, `git push`, or destructive Git commands.

## Validation and preview

After creating the post:

1. Run `bundle check`.
2. If dependencies are missing, report the exact missing dependency state.
   Install dependencies only after the user authorizes network and environment
   changes.
3. Run `bash tools/test.sh` for production build and internal-link checks.
4. Confirm the post was not skipped as future-dated and that its generated
   permalink exists under `_site/posts/<slug>/`.
5. Start `bash tools/run.sh` as a long-running local process.
6. Report the article file, inferred metadata, preview URL, validation result,
   and any pre-existing working-tree changes.

The workflow ends with local preview. The user performs commit and push.

## Error handling

- Missing H1: infer a title and report it.
- Empty article: stop without creating a post.
- Invalid or unclosed Front Matter: stop and identify the malformed block.
- Duplicate destination: stop without overwriting.
- Port 4000 occupied: report the process conflict and offer a different port.
- Jekyll build failure: keep the generated post, report the failing command and
  relevant output, and do not start preview.
- Preview process termination: report the exit status and leave the post intact.

## Testing

### Script tests

Use temporary Git repositories and verify:

- A body-only article receives the required Front Matter.
- Existing explicit metadata is preserved and missing fields are filled.
- The Markdown body remains unchanged.
- Non-`main` branches are rejected before writing.
- Duplicate destinations are not overwritten.
- Slugs and list values are validated.
- The example input produces metadata containing the concepts `博客`,
  `jekyll`, and `macos`.

### Skill validation

- Run `quick_validate.py` against the skill folder.
- Run script tests directly.
- Forward-test a fresh agent against a temporary copy of the blog repository.
- Confirm it creates one post, remains on `main`, starts or proposes the
  repository preview command, and does not commit or push.

## Non-goals

- Editing article prose.
- Generating illustrations.
- Managing Git history.
- Deploying GitHub Pages.
- Monitoring GitHub Actions.
- Publishing to WeChat or other platforms.
