import hashlib
import os
from typing import Optional

import certifi
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

app = FastAPI(title="BMRTA Transit API")

# --- 1. CORS CONFIGURATION (Enables GitHub Pages Communication) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from your GitHub Pages live domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. MONGODB ATLAS CONNECTION ---
DEFAULT_URI = (
    "mongodb://adminhostcyanx_db_user:f68KGSR7YvxYhU02@"
    "ac-fa8wfwr-shard-00-00.rspb5i0.mongodb.net:27017,"
    "ac-fa8wfwr-shard-00-01.rspb5i0.mongodb.net:27017,"
    "ac-fa8wfwr-shard-00-02.rspb5i0.mongodb.net:27017/"
    "BengaluruCityDB?ssl=true&replicaSet=atlas-xr7k4w-shard-0&authSource=admin&appName=bangalorecluster"
)

MONGO_URI = os.getenv("MONGO_URI", DEFAULT_URI)
DB_NAME = os.getenv("DB_NAME", "BengaluruCityDB")

client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]


# --- 3. NATIVE PASSWORD HASH (Zero external C-dependency issues) ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# --- 4. REQUEST DATA SCHEMAS ---
class SignupPayload(BaseModel):
    name: str
    email: str
    password: str


class LoginPayload(BaseModel):
    email: str
    password: str


class ProfileUpdatePayload(BaseModel):
    bio: Optional[str] = None
    moon_mode: Optional[bool] = None          # Ghost Mode
    theme: Optional[str] = None              # "light-theme" or "dark-theme"
    glory_tag: Optional[str] = None          # Glory title CSS class
    glory_html: Optional[str] = None         # Title formatted HTML
    avatar_html: Optional[str] = None
    avatar_bg: Optional[str] = None
    avatar_anim: Optional[str] = None
    banner_bg: Optional[str] = None
    banner_anim: Optional[str] = None


class WalletPayload(BaseModel):
    amount: float


class FeedbackPayload(BaseModel):
    subject: str
    message: str


# Helper to identify user from custom header or persistent cookie
def get_user_email(request: Request) -> str:
    email = request.headers.get("X-User-Email") or request.cookies.get("bmrta_user")
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized. Please log in.")
    return email


# --- 5. HEALTH CHECK / ROOT ---
@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "BMRTA Transit Backend",
        "database": "Connected to MongoDB Atlas",
    }


# --- 6. AUTHENTICATION ENDPOINTS ---
@app.post("/api/signup")
@app.post("/api/auth/register")
async def signup(data: SignupPayload, response: Response):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered.")

    base_username = data.email.split("@")[0].lower()
    initials = "".join([part[0].upper() for part in data.name.split()[:2]]) or "AV"

    user_doc = {
        "name": data.name,
        "email": data.email,
        "username": f"@{base_username}",
        "password": hash_password(data.password),
        "wallet_balance": 245.50,
        "co2_points": 5200.0,
        "travel_points": 0,
        "reward_level": 1,
        "travels_in_level": 0,
        "bio": "Eco-warrior & daily commuter. Let's save the planet one trip at a time!",
        "moon_mode": False,
        "theme": "light-theme",
        "glory_tag": "tag-commuter",
        "glory_html": '<i class="fa-solid fa-train-subway"></i> Daily Commuter',
        "avatar": {
            "html": initials,
            "bg": "linear-gradient(135deg, #007bff, #06b6d4)",
            "anim": "",
        },
        "banner": {
            "bg": "linear-gradient(135deg, #1e3a8a, #3b82f6)",
            "anim": "",
        },
        "inventory": {
            "unscratched": [],
            "active": [],
            "scratched": [],
        },
    }

    await db.users.insert_one(user_doc)
    response.set_cookie(key="bmrta_user", value=data.email, max_age=86400 * 30, httponly=False)
    return {
        "status": "success",
        "user": data.name,
        "email": data.email,
        "access_token": data.email,
    }


@app.post("/api/login")
@app.post("/api/auth/login")
async def login(data: LoginPayload, response: Response):
    user = await db.users.find_one({
        "email": data.email,
        "password": hash_password(data.password),
    })
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password.")

    response.set_cookie(key="bmrta_user", value=user["email"], max_age=86400 * 30, httponly=False)
    return {
        "status": "success",
        "name": user["name"],
        "email": user["email"],
        "access_token": user["email"],
    }


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("bmrta_user")
    return {"status": "success"}


# --- 7. USER PROFILE & PREFERENCE SYNC ---
@app.get("/api/user/me")
@app.get("/api/user/profile")
async def get_user_data(request: Request):
    email = get_user_email(request)
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.pop("_id", None)
    user.pop("password", None)
    return user


@app.put("/api/user/customize")
@app.put("/api/user/profile")
async def update_customizations(data: ProfileUpdatePayload, request: Request):
    email = get_user_email(request)
    update_fields = {}

    if data.bio is not None:
        update_fields["bio"] = data.bio
    if data.moon_mode is not None:
        update_fields["moon_mode"] = data.moon_mode
    if data.theme is not None:
        update_fields["theme"] = data.theme
    if data.glory_tag is not None:
        update_fields["glory_tag"] = data.glory_tag
    if data.glory_html is not None:
        update_fields["glory_html"] = data.glory_html

    if any(x is not None for x in [data.avatar_html, data.avatar_bg, data.avatar_anim]):
        update_fields["avatar.html"] = data.avatar_html
        update_fields["avatar.bg"] = data.avatar_bg
        update_fields["avatar.anim"] = data.avatar_anim

    if data.banner_bg is not None or data.banner_anim is not None:
        update_fields["banner.bg"] = data.banner_bg
        update_fields["banner.anim"] = data.banner_anim

    if update_fields:
        await db.users.update_one({"email": email}, {"$set": update_fields})

    return {"status": "success", "message": "Preferences saved to database."}


# --- 8. WALLET TOP-UP ---
@app.post("/api/user/wallet/topup")
@app.post("/api/wallet/topup")
async def topup_wallet(data: WalletPayload, request: Request):
    email = get_user_email(request)
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    new_balance = round(user.get("wallet_balance", 0.0) + data.amount, 2)
    await db.users.update_one({"email": email}, {"$set": {"wallet_balance": new_balance}})
    return {"status": "success", "wallet_balance": new_balance}


# --- 9. LEADERBOARD (MONGODB ATLAS) ---
@app.get("/api/transit/leaderboard")
async def get_leaderboard():
    cursor = (
        db.users.find(
            {"moon_mode": {"$ne": True}},  # Ghost Mode users stay hidden from public leaderboard
            {"name": 1, "username": 1, "co2_points": 1, "avatar": 1, "banner": 1},
        )
        .sort("co2_points", -1)
        .limit(20)
    )

    users = await cursor.to_list(length=20)
    for u in users:
        u.pop("_id", None)
    return users


# --- 10. FEEDBACK & SUPPORT ---
@app.post("/api/support/feedback")
async def submit_feedback(data: FeedbackPayload, request: Request):
    email = get_user_email(request)
    doc = {
        "email": email,
        "subject": data.subject,
        "message": data.message,
    }
    await db.feedbacks.insert_one(doc)
    return {"status": "success", "message": "Feedback recorded."}


# --- 11. DYNAMIC RENDER RUNNER ---
if __name__ == "__main__":
    import uvicorn
    # Render binds dynamically to the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)