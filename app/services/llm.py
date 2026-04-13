from langchain_openai import ChatOpenAI

from app.core.config import settings

# Primary model – used for content generation & SEO analysis
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.openai_api_key,
    temperature=0.7,
    streaming=True,
)

# Fast model – used for routing decisions, keyword extraction, short tasks
llm_fast = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.openai_api_key,
    temperature=0.3,
    streaming=True,
)
