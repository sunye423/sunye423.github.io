# Chirpy Site Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure, verify, and publish the Chirpy site at `https://sunye423.github.io`.

**Architecture:** Keep the official Chirpy Starter structure and customize only site metadata, the About tab, and the first post. Use the bundled GitHub Actions workflow to build and deploy the generated Jekyll site.

**Tech Stack:** Jekyll, Chirpy 7.6, Ruby 3.4, GitHub Actions, GitHub Pages

## Global Constraints

- Use `zh-CN` and `Asia/Shanghai` for site localization.
- Publish at `https://sunye423.github.io` with an empty `baseurl`.
- Do not enable services that require unknown account identifiers.

---

### Task 1: Configure site identity and content

**Files:**
- Modify: `_config.yml`
- Modify: `_tabs/about.md`
- Create: `_posts/2026-07-21-hello-chirpy.md`

- [ ] Set the site URL, locale, timezone, title, description, and GitHub identity.
- [ ] Replace the About placeholder with concise public information.
- [ ] Add the first post with valid Chirpy front matter.

### Task 2: Verify production output

**Files:**
- Generated and ignored: `_site/`

- [ ] Run `bundle install` and expect exit code 0.
- [ ] Run `JEKYLL_ENV=production bundle exec jekyll build` and expect exit code 0.
- [ ] Run `bundle exec htmlproofer _site --disable-external` and expect exit code 0.

### Task 3: Publish to GitHub Pages

**Files:**
- Use existing: `.github/workflows/pages-deploy.yml`

- [ ] Commit only the intended configuration, About page, post, and plan.
- [ ] Push `main` to `origin` as requested for the initial site deployment.
- [ ] Configure Pages to use GitHub Actions and verify the deployment run.
