"""
User Authentication API Routes

Provides endpoints for user registration, login, and profile management.
"""

from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    get_token_expiry_seconds,
    hash_password,
    verify_password,
)
from app.db.mongo import get_db
from app.db.es import es_client
from app.schemas.response import ResponseBase, success_response, error_response
from app.schemas.user import (
    Token,
    UserCreate,
    UserInDB,
    UserLogin,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=ResponseBase[UserResponse])
async def register(user_data: UserCreate, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Register a new user account.

    - **username**: Unique username (3-32 chars, alphanumeric)
    - **email**: Valid email address
    - **password**: Password (min 6 chars)
    """
    # Check if username exists
    existing = await db.users.find_one({"username": user_data.username})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already registered"
        )

    # Check if email exists
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    # Create user document
    now = datetime.utcnow()
    user_doc = {
        "username": user_data.username,
        "email": user_data.email,
        "hashed_password": hash_password(user_data.password),
        "avatar_url": None,
        "settings": {},
        "created_at": now,
        "updated_at": now,
        "is_active": True,
    }

    # Insert into database
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    # Create user's Elasticsearch index
    await es_client.ensure_user_index(user_id)

    # Build response
    user_response = UserResponse(
        id=user_id,
        username=user_data.username,
        email=user_data.email,
        avatar_url=None,
        settings={},
        created_at=now,
    )

    return success_response(data=user_response, message="Registration successful")


@router.post("/login", response_model=ResponseBase[Token])
async def login(credentials: UserLogin, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Authenticate user and return JWT token.

    - **username**: Username or email
    - **password**: User password
    """
    # Find user by username or email
    user = await db.users.find_one(
        {"$or": [{"username": credentials.username}, {"email": credentials.username}]}
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # Verify password
    if not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # Check if user is active
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )

    # Generate token
    user_id = str(user["_id"])
    access_token = create_access_token(subject=user_id)

    token = Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_token_expiry_seconds(),
    )

    return success_response(data=token, message="Login successful")


@router.get("/me", response_model=ResponseBase[UserResponse])
async def get_me(current_user: UserInDB = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    user_response = UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        settings=current_user.settings,
        created_at=current_user.created_at,
    )

    return success_response(data=user_response)


@router.patch("/me", response_model=ResponseBase[UserResponse])
async def update_me(
    update_data: UserUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update current user's profile."""
    # Build update document
    update_fields = {}

    if update_data.email is not None:
        # Check if email is taken by another user
        existing = await db.users.find_one(
            {"email": update_data.email, "_id": {"$ne": ObjectId(current_user.id)}}
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already in use"
            )
        update_fields["email"] = update_data.email

    if update_data.avatar_url is not None:
        update_fields["avatar_url"] = update_data.avatar_url

    if update_data.settings is not None:
        update_fields["settings"] = update_data.settings

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    update_fields["updated_at"] = datetime.utcnow()

    # Update in database
    await db.users.update_one(
        {"_id": ObjectId(current_user.id)}, {"$set": update_fields}
    )

    # Fetch updated user
    updated_user = await db.users.find_one({"_id": ObjectId(current_user.id)})

    user_response = UserResponse(
        id=str(updated_user["_id"]),
        username=updated_user["username"],
        email=updated_user["email"],
        avatar_url=updated_user.get("avatar_url"),
        settings=updated_user.get("settings", {}),
        created_at=updated_user["created_at"],
    )

    return success_response(data=user_response, message="Profile updated")
