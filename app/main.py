from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import pages FIRST — before any LangGraph modules — so Jinja2
# initialises its cache before StateGraph(dict) can interfere.
from app.api.pages import router as pages_router
from app.api.routes import router as api_router

app = FastAPI(
    title="BlogForge — AI Blog Generator",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix="/api")

# Page routes (served at root)
app.include_router(pages_router)

# Static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health():
    return {"status": "healthy"}
