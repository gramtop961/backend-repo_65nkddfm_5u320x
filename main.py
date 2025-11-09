import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImageGenRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    count: int = Field(10, ge=1, le=50)
    style: Optional[str] = Field(None, description="Optional style preset")
    references: Optional[List[HttpUrl]] = None


class ImageGenResponse(BaseModel):
    job_id: str
    images: List[str]
    provider: str


class VideoGenRequest(BaseModel):
    script: str = Field(..., min_length=3)
    aspect_ratio: str = Field("9:16")
    duration_seconds: int = Field(8, ge=4, le=30)
    voice: Optional[str] = None
    tone: Optional[str] = None
    references: Optional[List[HttpUrl]] = None


class VideoGenResponse(BaseModel):
    job_id: str
    video_url: str
    provider: str


KEYAI_API_KEY = os.getenv("KEYAI_API_KEY")
KEYAI_BASE = os.getenv("KEYAI_BASE", "https://api.key.ai")


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db  # type: ignore
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:  # pragma: no cover
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:  # pragma: no cover
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


@app.post("/api/generate/images", response_model=ImageGenResponse)
def generate_images(req: ImageGenRequest):
    """Integrates Nano Banana (via key.ai) if KEYAI_API_KEY is present. Otherwise returns realistic placeholders.
    """
    provider = "mock"
    images: List[str] = []

    if KEYAI_API_KEY:
        try:
            # NOTE: Example call; adjust to actual key.ai schema if different.
            # This code is defensive: if provider schema changes, we fall back to mock below.
            headers = {"Authorization": f"Bearer {KEYAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "nano-banana",
                "input": {
                    "prompt": req.prompt,
                    "num_images": req.count,
                    "style": req.style,
                    "references": req.references or []
                }
            }
            r = requests.post(f"{KEYAI_BASE}/v1/images/generate", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                urls = []
                # Try common fields defensively
                if isinstance(data, dict):
                    if "images" in data and isinstance(data["images"], list):
                        urls = [img.get("url") for img in data["images"] if isinstance(img, dict) and img.get("url")]
                    elif "data" in data and isinstance(data["data"], list):
                        urls = [item.get("url") for item in data["data"] if isinstance(item, dict) and item.get("url")]
                if urls:
                    provider = "key.ai:nano-banana"
                    images = urls[: req.count]
            # if any problem, fall through to mock
        except Exception:  # pragma: no cover
            pass

    if not images:
        # Mock using picsum with seeded queries for visual variety
        seed_base = req.prompt.replace(" ", "+")[:40]
        images = [
            f"https://picsum.photos/seed/{seed_base}-{i}/768/1024" for i in range(req.count)
        ]

    return ImageGenResponse(job_id="job_img_" + str(abs(hash(req.prompt)) % 10_000_000), images=images, provider=provider)


@app.post("/api/generate/video", response_model=VideoGenResponse)
def generate_video(req: VideoGenRequest):
    """Integrates Veo 3.1 (via key.ai) if KEYAI_API_KEY present; otherwise returns a demo clip URL."""
    provider = "mock"
    video_url = ""

    if KEYAI_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {KEYAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "veo-3.1",
                "input": {
                    "script": req.script,
                    "aspect_ratio": req.aspect_ratio,
                    "duration": req.duration_seconds,
                    "voice": req.voice,
                    "tone": req.tone,
                    "references": req.references or []
                }
            }
            r = requests.post(f"{KEYAI_BASE}/v1/video/generate", json=payload, headers=headers, timeout=120)
            if r.status_code == 200:
                data = r.json()
                # Try common fields defensively
                if isinstance(data, dict):
                    video_url = data.get("url") or data.get("video_url") or ""
                    if not video_url and "data" in data and isinstance(data["data"], dict):
                        video_url = data["data"].get("url") or data["data"].get("video_url") or ""
                if video_url:
                    provider = "key.ai:veo-3.1"
        except Exception:  # pragma: no cover
            pass

    if not video_url:
        # Public demo video asset (short, for preview only)
        video_url = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"

    return VideoGenResponse(job_id="job_vid_" + str(abs(hash(req.script)) % 10_000_000), video_url=video_url, provider=provider)


class SubscribeRequest(BaseModel):
    plan: str
    email: Optional[str] = None


@app.post("/api/subscribe")
def subscribe(req: SubscribeRequest):
    # Normally store in DB / send email; keeping simple here
    if req.plan not in {"Free", "Creator", "Pro"}:
        raise HTTPException(status_code=400, detail="Invalid plan")
    return {"status": "ok", "message": f"Subscribed to {req.plan}", "email": req.email}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
