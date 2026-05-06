# BlogForge — Quick Reference

## What's Running

| Container | URL | Purpose |
|-----------|-----|---------|
| `blog-gen-api` | http://localhost:8000 | BlogForge app |
| `blog-gen-wp` | http://localhost:18888 | WordPress (test target) |
| `blog-gen-wp-db` | — | MariaDB for WordPress |

## Credentials

| Service | Username | Password |
|---------|----------|----------|
| BlogForge | Register on login page | — |
| WordPress Admin | `admin` | `admin123` |

## Setup (first time only)

```bash
cp .env.example .env
# Add your OpenAI and Brave API keys to .env

docker compose up --build -d
./setup-wp.sh
```

The setup script will:
- Install WP-CLI and WordPress
- Enable pretty permalinks
- Enable application passwords
- Create an application password and save to `.env`

## Workflow

1. **Generate** — Enter your blog topic
   - Research findings appear in a collapsible card
   - SEO analysis appears (score, keywords, suggestions)
   - Blog content streams in word-by-word

2. **Review** — Read the blog, check the research and SEO cards

3. **Revise** — Type feedback to improve the content:
   - "Make the intro shorter"
   - "Add a section about ethics"
   - "Use more casual tone"
   - The blog rewrites automatically

4. **Publish** — Click "Publish to WordPress" when happy
   - Post is saved as a **draft** in WordPress
   - Link goes to WordPress Admin to view/edit
   - Log in to publish the draft publicly

## Published Post Fields

When publishing to WordPress, the following fields are set:

| Field | Value |
|-------|-------|
| `title` | Blog title |
| `slug` | Auto-generated from title (URL-friendly) |
| `content` | Blog content (HTML) |
| `excerpt` | SEO meta description (first 200 chars) |
| `status` | `draft` |
| `author` | `1` (admin) |
| `categories` | Default category (uncategorized) |

Example payload sent to WordPress:
```json
{
  "title": "Mastering REST API Design Patterns",
  "slug": "mastering-rest-api-design-patterns",
  "content": "<p>Blog content here...</p>",
  "excerpt": "SEO meta description...",
  "status": "draft",
  "author": 1
}
```

## URLs

| Purpose | URL |
|---------|-----|
| BlogForge App | http://localhost:8000 |
| WordPress Admin | http://localhost:18888/wp-admin |
| WordPress Home | http://localhost:18888 |

## Troubleshooting

**Permalink shows `http://wordpress/...`**
- This is a Docker internal hostname. Use the admin link to view drafts.

**"Session not found" error**
- Container was restarted — sessions are in-memory. Start a new chat.

**OpenAI/Brave errors**
- Check `.env` has valid API keys.
- Restart: `docker compose restart blog-gen`

**Publish returns 401 error**
- Run `./setup-wp.sh` to generate a fresh application password.
- Verify `WORDPRESS_APP_PASSWORD` in `.env` matches.
