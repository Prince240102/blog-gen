# BlogForge

AI-powered blog generator with a multi-agent LangGraph pipeline.

**Agents:** Research (Brave Search) → SEO Optimiser → Content Generator → WordPress Publisher

## Quick Start

```bash
cp .env.example .env   # fill in your API keys
docker compose up --build -d
./setup-wp.sh          # configure WordPress (one-time)
```

| Service | URL |
|---|---|
| BlogForge | http://localhost:8000 |
| WordPress | http://localhost:18888 |
| WP Admin | http://localhost:18888/wp-admin (admin / admin123) |

## How It Works

```
User sends topic
      │
      ▼
  🔍 Research (Brave Search)
      │
      ▼
  ⭐ SEO Analysis (keywords, score, meta)
      │
      ▼
  ✍️ Blog Content (GPT-4o, streams word-by-word)
      │
      ▼
  👤 User reviews → requests changes → content revises
      │
      ▼
  📤 Publish to WordPress as draft
```

## Review Loop

1. **Generate** — agents research, optimize SEO, and write the blog
2. **Review** — see research findings and SEO analysis in collapsible cards
3. **Revise** — type feedback ("make intro shorter", "add section on ethics") and the blog rewrites
4. **Publish** — click "Publish to WordPress" when you're happy

## Architecture

- **Backend:** FastAPI with JWT auth, SSE streaming, in-memory sessions
- **Frontend:** Jinja2 templates + vanilla JS (no framework)
- **AI:** OpenAI GPT-4o via LangChain, Brave Search API via httpx
- **WordPress:** REST API with application passwords

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `BRAVE_API_KEY` | Brave Search API key |
| `WORDPRESS_URL` | WordPress URL (default: `http://wordpress`) |
| `WORDPRESS_USERNAME` | WordPress username |
| `WORDPRESS_APP_PASSWORD` | WordPress application password |
| `JWT_SECRET` | Secret for JWT tokens |
