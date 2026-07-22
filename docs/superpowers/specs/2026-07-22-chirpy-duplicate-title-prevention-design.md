# Chirpy Duplicate Title Prevention Design

## Goal

Prevent a Chirpy article title from appearing twice when the source Markdown
starts with an H1 that duplicates the effective Front Matter `title`.

The source Markdown remains unchanged. Only the generated post body may remove
one redundant leading title heading.

## Root cause

Chirpy renders the Front Matter `title` as the page heading. The current
publishing helper also preserves the source Markdown body byte-for-byte. When
that body begins with the same H1, Jekyll renders a second visible title.

## Selected approach

Implement deterministic duplicate-heading removal in `prepare_post.py` rather
than relying on agent judgment or theme CSS.

After Front Matter values are merged and the effective title is known, inspect
the start of the Markdown body. Remove the leading H1 only when its normalized
visible text equals the normalized effective title.

## Matching rules

- Ignore a UTF-8 BOM and blank lines before the first body element.
- Recognize an ATX H1 whose marker is exactly one `#` followed by whitespace.
- Recognize a Setext H1 whose text line is followed by an `=` underline.
- Normalize both candidate heading and effective title by:
  - trimming leading and trailing whitespace;
  - collapsing consecutive whitespace;
  - removing common inline Markdown presentation from emphasis, strikethrough,
    code spans, and links while retaining visible link text;
  - removing optional closing ATX `#` markers.
- Remove the heading only when the normalized strings are equal and non-empty.
- Remove at most one immediately following blank line to avoid an artificial
  gap at the start of the article.

## Preservation rules

- Never modify the input Markdown file.
- Preserve every body byte after the removed heading and its one optional blank
  line.
- Preserve a leading H1 when it differs from the effective title.
- Preserve H1 elements that occur after another non-blank body element.
- Preserve bodies without an H1.
- Existing Front Matter preservation, safe paths, no-clobber publication, Git
  boundaries, request-file security, and permalink behavior remain unchanged.

## Skill instructions

Update `SKILL.md` to state that generated Chirpy posts must not retain a leading
H1 that duplicates the effective Front Matter title. Replace the unconditional
body-exactness claim with the precise exception for this redundant heading.

Keep the personal skill at:

```text
/Users/sunye/.codex/skills/publishing-chirpy-blog
```

and the repository copy at:

```text
.codex/skills/publishing-chirpy-blog
```

identical after the change.

## Current article

The already generated post
`_posts/2026-07-22-build-jekyll-chirpy-blog-on-macos.md` is untracked. Remove
its duplicate leading H1 while leaving its Front Matter and remaining body
unchanged. LiveReload should update the existing local preview.

## Testing

Add tests before implementation and observe them fail for the missing behavior.
Cover:

- matching leading ATX H1 removal;
- matching leading Setext H1 removal;
- Markdown-formatted visible title matching;
- preservation of a different leading H1;
- preservation of a matching H1 after another body element;
- preservation of bodies without H1;
- preservation of all bytes after the removed heading boundary;
- source file hash remains unchanged;
- skill wording documents the duplicate-title rule;
- installed and repository skill copies remain identical.

Run the complete helper test suite, official skill validation, Jekyll production
build, artifact verification, and HTTP preview verification. Stop without
committing or pushing the article or skill update.
