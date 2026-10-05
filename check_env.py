# 环境连通性检查：PostgreSQL + Milvus
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from pymilvus import connections, utility

# 连接信息统一从环境变量读取（参考 .env.example），避免硬编码
DB_USER = os.getenv("DB_USER", "eduagent_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "eduagent")
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19531"))

DB_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


async def check_postgres():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 1"))
        print("PostgreSQL 连通 ✓", r.scalar())
    await engine.dispose()


def check_milvus():
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    print("Milvus 连通（已有集合）：", utility.list_collections())


async def main():
    await check_postgres()
    check_milvus()


asyncio.run(main())
