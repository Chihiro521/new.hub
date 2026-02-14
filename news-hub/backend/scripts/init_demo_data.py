"""
Initialize Demo Data

Populates the database with a demo user, sources, and tag rules for defense presentation.

Usage:
    cd backend
    python scripts/init_demo_data.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
from passlib.context import CryptContext

from app.db.mongo import mongodb
from app.services.tagging import TagService
from app.schemas.tag import TagRuleCreate, MatchMode

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def init_demo_data():
    """Main initialization function."""
    logger.info("Initializing demo data...")

    # Connect to DB
    await mongodb.connect()
    db = mongodb.db

    try:
        # 1. Create Demo User
        demo_user = await db.users.find_one({"username": "demo"})
        if not demo_user:
            logger.info("Creating demo user...")
            hashed_password = pwd_context.hash("demo123")
            result = await db.users.insert_one(
                {
                    "username": "demo",
                    "email": "demo@newshub.com",
                    "hashed_password": hashed_password,
                    "is_active": True,
                    "created_at": datetime.utcnow(),
                }
            )
            user_id = str(result.inserted_id)
        else:
            logger.info("Demo user already exists")
            user_id = str(demo_user["_id"])

        # 2. Add Sources (Direct DB insertion)
        existing_sources_cursor = db.sources.find({"user_id": user_id})
        existing_sources = await existing_sources_cursor.to_list(length=100)
        existing_urls = {s["url"] for s in existing_sources}

        demo_sources = [
            {
                "name": "36Kr",
                "url": "https://36kr.com/feed",
                "source_type": "rss",
                "description": "Tech news and startup coverage",
            },
            {
                "name": "V2EX",
                "url": "https://www.v2ex.com/index.xml",
                "source_type": "rss",
                "description": "Creative worker community",
            },
            {
                "name": "InfoQ",
                "url": "https://feed.infoq.com/",
                "source_type": "rss",
                "description": "Software development news",
            },
            {
                "name": "Hacker News",
                "url": "https://news.ycombinator.com/rss",
                "source_type": "rss",
                "description": "Tech news and discussions",
            },
            {
                "name": "OSChina",
                "url": "https://www.oschina.net/news/rss",
                "source_type": "rss",
                "description": "Open source community news",
            },
        ]

        now = datetime.utcnow()
        for src in demo_sources:
            if src["url"] not in existing_urls:
                logger.info(f"Adding source: {src['name']}")
                source_doc = {
                    "user_id": user_id,
                    "name": src["name"],
                    "url": src["url"],
                    "source_type": src["source_type"],
                    "description": src["description"],
                    "logo_url": None,
                    "homepage": None,
                    "tags": [],
                    "parser_config": None,
                    "refresh_interval_minutes": 60,
                    "status": "pending",
                    "last_fetched_at": None,
                    "last_error": None,
                    "fetch_count": 0,
                    "item_count": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                await db.sources.insert_one(source_doc)

        # 3. Add Tag Rules
        tag_service = TagService(db)
        existing_rules = await tag_service.list_rules(user_id)
        existing_tags = {r["tag_name"] for r in existing_rules}

        demo_rules = [
            {
                "tag_name": "AI",
                "keywords": [
                    "AI",
                    "Artificial Intelligence",
                    "LLM",
                    "GPT",
                    "Deep Learning",
                    "Machine Learning",
                    "人工智能",
                    "大模型",
                ],
                "priority": 10,
            },
            {
                "tag_name": "Frontend",
                "keywords": [
                    "Vue",
                    "React",
                    "Angular",
                    "CSS",
                    "JavaScript",
                    "TypeScript",
                    "Web",
                    "前端",
                ],
                "priority": 5,
            },
            {
                "tag_name": "Backend",
                "keywords": [
                    "Python",
                    "Java",
                    "Go",
                    "Rust",
                    "FastAPI",
                    "Django",
                    "Spring",
                    "后端",
                    "Database",
                    "SQL",
                ],
                "priority": 5,
            },
            {
                "tag_name": "Startup",
                "keywords": [
                    "Startup",
                    "Funding",
                    "VC",
                    "Investment",
                    "创业",
                    "融资",
                    "IPO",
                ],
                "priority": 3,
            },
            {
                "tag_name": "Cloud",
                "keywords": [
                    "Cloud",
                    "AWS",
                    "Azure",
                    "Kubernetes",
                    "Docker",
                    "DevOps",
                    "云原生",
                    "云计算",
                ],
                "priority": 4,
            },
        ]

        for rule in demo_rules:
            if rule["tag_name"] not in existing_tags:
                logger.info(f"Adding tag rule: {rule['tag_name']}")
                await tag_service.create_rule(
                    user_id,
                    TagRuleCreate(
                        tag_name=rule["tag_name"],
                        keywords=rule["keywords"],
                        priority=rule["priority"],
                        match_mode=MatchMode.ANY,
                        match_title=True,
                        match_description=True,
                        match_content=False,
                    ),
                )

        logger.success("Demo data initialization complete!")
        logger.info(f"Login with: demo / demo123")

    finally:
        await mongodb.disconnect()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(init_demo_data())
