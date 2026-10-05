import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# sqlite,mysql,pg都属于典型的关系型数据库，我们这里只是想给的大家演示：sqlalchemy的基本功能，所以用了sqlite
"""
    url : 数据库类型+驱动://连接信息
    sqlite: sqlite+aiosqlite:///demo.db
    mysql: mysql+aiomysql://user:password@host:port/dbname
    pg: postgresql+asyncpg://user:password@host:port/dbname
"""
engine = create_async_engine("sqlite+aiosqlite:///demo.db") # 创建引擎
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
# 建引擎 → 建会话工厂 → 用会话：
async def main():

    async with AsyncSessionLocal() as session:
        # 建表（项目里由 init_db.sql 完成，这里为了演示临时建一张） text(sql) 原始sql语句
        await session.execute(text("DROP TABLE IF EXISTS users"))
        await session.execute(text("""
            CREATE TABLE users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT,
                role      TEXT,
                is_active BOOLEAN
            )
        """))

        # 增（INSERT）：参数化查询:参数化sql 占位符格式 -> :键
        # 防止sql注入“ ： 占位的内容只会当做值，不会当做sql语句执行
        # [{}] 批量插入
        # await session.execute(
        #     text("INSERT INTO users (username, role, is_active) VALUES (:u, :r, :a)"),
        #     [
        #         {"u": "student01", "r": "student", "a": True},
        #         {"u": "student02", "r": "student", "a": True}
        #     ]
        # )
        s = r"student02'  ,'12','1'); DROP TABLE users; --"
        # INSERT INTO users (username, role, is_active) VALUES ('student02';DROP TABLE users;   --
        await session.execute(
            text(f"INSERT INTO users (username, role, is_active) VALUES ('{s}', 'student', True)"  )
        )

        # await session.execute(
        #     text("INSERT INTO users (username, role, is_active) VALUES (:u, :r, :a)"),
        #     {"u": "teacher01", "r": "teacher", "a": True},
        # )
        # # 查（SELECT）
        # result = await session.execute(
        #     text("SELECT id, username, role, is_active FROM users WHERE role = :r"),
        #     {"r": "student"},
        # )
        # row = result.fetchone() # 返回的是一行数据，类型是元组
        # # row = result.fetchall()  # 返回的是所有行的数据，类型是列表
        # print(f'row-->{row}')
        # print("查到学生：", row.id, row.username, row.role, row.is_active)
        # # print("查到学生：", row[0], row[1], row[2])
        # # print("*"*80)
        # # #
        # # # 改（UPDATE）
        # await session.execute(
        #     text("UPDATE users SET is_active = :a WHERE username = :u"),
        #     {"a": False, "u": "student01"},
        # )
        # result = await session.execute(
        #     text("SELECT id, username, role, is_active FROM users"))
        # row = result.fetchall()
        # print(f'row-->{row}')
        # print("*"*80)
        # # #
        # # # 删（DELETE）
        # await session.execute(
        #     text("DELETE FROM users WHERE username = :u"),
        #     {"u": "teacher01"},
        # )
        # #
        # 提交事务：让上面所有改动真正生效
        await session.commit()
        # result = await session.execute(
        #     text("SELECT * FROM users")
        # )
        # print(result.fetchall())

asyncio.run(main())
