from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.brand.router import router as brand_router
from app.campaign.router import router as campaign_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="AI Landing Page Generator API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brand_router, prefix="/api")
app.include_router(campaign_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
