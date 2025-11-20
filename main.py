import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from hashlib import sha256
import secrets

from database import db
from schemas import Category, Product, Order, AdminUser

app = FastAPI(title="Handestiy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------- Helpers ----------------------

def hash_password(password: str) -> str:
    return sha256(password.encode()).hexdigest()

class TokenInfo(BaseModel):
    token: str
    expires_at: datetime

# ---------------------- Schema endpoint ----------------------
@app.get("/schema")
def get_schema():
    return {
        "category": Category.model_json_schema(),
        "product": Product.model_json_schema(),
        "order": Order.model_json_schema(),
        "adminuser": AdminUser.model_json_schema(),
    }

# ---------------------- Health ----------------------
@app.get("/")
def root():
    return {"brand": "Handestiy", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": os.getenv("DATABASE_NAME") or "❌ Not Set",
        "collections": []
    }
    try:
        if db is None:
            response["database"] = "❌ Not Connected"
        else:
            response["database"] = "✅ Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:120]}"
    return response

# ---------------------- Auth utils ----------------------

def get_admin_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    admin = db["adminuser"].find_one({"current_token.token": token})
    if admin and admin.get("current_token", {}).get("expires_at"):
        if datetime.now(timezone.utc) > admin["current_token"]["expires_at"]:
            return None
    return admin

async def require_admin(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1]
    admin = get_admin_by_token(token)
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return admin

# ---------------------- Seed admin ----------------------
class SeedAdminBody(BaseModel):
    email: str
    password: str

@app.post("/api/admin/seed")
def seed_admin(body: SeedAdminBody):
    existing = db["adminuser"].find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")
    db["adminuser"].insert_one({
        "email": body.email,
        "password": hash_password(body.password),
        "created_at": datetime.now(timezone.utc)
    })
    return {"created": True}

# ---------------------- Admin login ----------------------
class LoginBody(BaseModel):
    email: str
    password: str

@app.post("/api/admin/login", response_model=TokenInfo)
def admin_login(body: LoginBody):
    admin = db["adminuser"].find_one({"email": body.email})
    if not admin or admin.get("password") != hash_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(24)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
    db["adminuser"].update_one({"_id": admin["_id"]}, {"$set": {"current_token": {"token": token, "expires_at": expires_at}}})
    return TokenInfo(token=token, expires_at=expires_at)

# ---------------------- Categories ----------------------
@app.get("/api/categories")
def list_categories(active: Optional[bool] = Query(default=True)):
    q = {"active": True} if active else {}
    cats = list(db["category"].find(q).sort("name", 1))
    for c in cats:
        c["_id"] = str(c["_id"])
    return cats

class CategoryUpsert(Category):
    pass

@app.post("/api/admin/categories")
def create_category(body: CategoryUpsert, admin=Depends(require_admin)):
    if db["category"].find_one({"slug": body.slug}):
        raise HTTPException(status_code=400, detail="Slug already exists")
    res = db["category"].insert_one({**body.model_dump(), "created_at": datetime.now(timezone.utc)})
    return {"_id": str(res.inserted_id)}

@app.put("/api/admin/categories/{cat_id}")
def update_category(cat_id: str, body: CategoryUpsert, admin=Depends(require_admin)):
    try:
        _id = ObjectId(cat_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    db["category"].update_one({"_id": _id}, {"$set": body.model_dump()})
    return {"updated": True}

@app.delete("/api/admin/categories/{cat_id}")
def delete_category(cat_id: str, admin=Depends(require_admin)):
    try:
        _id = ObjectId(cat_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    db["category"].delete_one({"_id": _id})
    return {"deleted": True}

# ---------------------- Products ----------------------
@app.get("/api/products")
def list_products(
    category: Optional[str] = None,
    sort: Optional[str] = Query(default="newest"),
    page: int = 1,
    limit: int = 12,
):
    q = {"active": True}
    if category and category != "All":
        q["category"] = category
    cursor = db["product"].find(q)
    if sort == "price_asc":
        cursor = cursor.sort("price", 1)
    elif sort == "price_desc":
        cursor = cursor.sort("price", -1)
    else:  # newest
        cursor = cursor.sort("created_at", -1)
    total = cursor.count() if hasattr(cursor, 'count') else db["product"].count_documents(q)
    cursor = cursor.skip((page-1)*limit).limit(limit)
    items = []
    for p in cursor:
        p["_id"] = str(p["_id"])
        items.append(p)
    return {"items": items, "total": total, "page": page, "limit": limit}

@app.get("/api/products/{slug}")
def get_product_by_slug(slug: str):
    p = db["product"].find_one({"slug": slug, "active": True})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    p["_id"] = str(p["_id"])
    return p

@app.get("/api/products/id/{pid}")
def get_product_by_id(pid: str):
    try:
        _id = ObjectId(pid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    p = db["product"].find_one({"_id": _id})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    p["_id"] = str(p["_id"])
    return p

class ProductUpsert(Product):
    pass

@app.post("/api/admin/products")
def create_product(body: ProductUpsert, admin=Depends(require_admin)):
    if db["product"].find_one({"slug": body.slug}):
        raise HTTPException(status_code=400, detail="Slug already exists")
    res = db["product"].insert_one({**body.model_dump(), "created_at": datetime.now(timezone.utc)})
    return {"_id": str(res.inserted_id)}

@app.put("/api/admin/products/{pid}")
def update_product(pid: str, body: ProductUpsert, admin=Depends(require_admin)):
    try:
        _id = ObjectId(pid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    db["product"].update_one({"_id": _id}, {"$set": body.model_dump()})
    return {"updated": True}

@app.delete("/api/admin/products/{pid}")
def delete_product(pid: str, admin=Depends(require_admin)):
    try:
        _id = ObjectId(pid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    db["product"].delete_one({"_id": _id})
    return {"deleted": True}

# ---------------------- Orders ----------------------
@app.post("/api/orders")
def create_order(order: Order):
    data = order.model_dump()
    data["created_at"] = datetime.now(timezone.utc)
    res = db["order"].insert_one(data)
    return {"order_id": str(res.inserted_id)}

@app.get("/api/orders/{oid}")
def get_order(oid: str):
    try:
        _id = ObjectId(oid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    o = db["order"].find_one({"_id": _id})
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    o["_id"] = str(o["_id"])
    return o

@app.get("/api/admin/orders")
def list_orders(status: Optional[str] = None, search: Optional[str] = None, admin=Depends(require_admin)):
    q = {}
    if status:
        q["status"] = status
    if search:
        q["$or"] = [
            {"customer.name": {"$regex": search, "$options": "i"}},
            {"customer.email": {"$regex": search, "$options": "i"}},
        ]
    items = []
    for o in db["order"].find(q).sort("created_at", -1):
        o["_id"] = str(o["_id"])
        items.append(o)
    return items

class UpdateStatusBody(BaseModel):
    status: str

@app.patch("/api/admin/orders/{oid}/status")
def update_order_status(oid: str, body: UpdateStatusBody, admin=Depends(require_admin)):
    try:
        _id = ObjectId(oid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    db["order"].update_one({"_id": _id}, {"$set": {"status": body.status}})
    return {"updated": True}
