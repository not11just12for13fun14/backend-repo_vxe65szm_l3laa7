"""
Database Schemas for Handestiy E-commerce

Each Pydantic model represents a collection in MongoDB. The collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

class Category(BaseModel):
    name: str = Field(..., description="Category name")
    slug: str = Field(..., description="Unique slug for category")
    description: Optional[str] = Field(None, description="Category description")
    active: bool = Field(True, description="Whether the category is visible")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    slug: str = Field(..., description="URL slug")
    short_description: Optional[str] = Field(None, description="Short description")
    long_description: Optional[str] = Field(None, description="Detailed description")
    price: float = Field(..., ge=0, description="Price")
    discount_price: Optional[float] = Field(None, ge=0, description="Discounted price")
    category: str = Field(..., description="Category slug")
    stock: int = Field(..., ge=0, description="Available quantity")
    materials: Optional[str] = Field(None, description="Materials used")
    dimensions: Optional[str] = Field(None, description="Dimensions / size")
    images: List[str] = Field(default_factory=list, description="List of image URLs")
    active: bool = Field(True, description="Whether product is visible")

class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int
    image: Optional[str] = None

class CustomerInfo(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: str

class Order(BaseModel):
    items: List[OrderItem]
    subtotal: float
    shipping: float
    total: float
    customer: CustomerInfo
    shipping_method: Literal['Standard Shipping','Express Shipping'] = 'Standard Shipping'
    status: Literal['Pending','Shipped','Delivered','Cancelled'] = 'Pending'
    created_at: Optional[datetime] = None

class AdminUser(BaseModel):
    email: EmailStr
    password: str
