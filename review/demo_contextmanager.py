# class ResourceManager:
#     def __enter__(self):
#         print("1. 管家：已进入房间，空调已打开")
#         return "这是一把房间钥匙"  # 返回给 with 后面的 as 变量
#
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         # print(f"exc_type-->{exc_type}")
#         # print(f"exc_val-->{exc_val}")
#         print("2. 管家：正在退出，垃圾已带走，空调已关闭")
#         # 返回 True 表示吞掉异常，返回 False 表示向外抛出异常
#
#
# # 测试运行
# with ResourceManager() as key:
#     # 即使这里报错，管家也会先执行关门再报错
#     # raise ValueError("不小心打碎杯子")
#     print(f"3. 我在房间里干活，拿着 {key}")

# 输出顺序：1 -> 3 -> 2
# from contextlib import contextmanager
#
# @contextmanager
# def ResourceManager():
#     print("1. 开门，开空调")
#     try:
#         yield "钥匙"  # 分界线，相当于 __enter__ 的返回值
#     finally:
#         # finally 保证即使报错也会执行关门
#         print("2. 关门，关空调，清理垃圾")
#
# # 使用
# with ResourceManager() as key:
#     print(f"3. 干活中，拿着 {key}")
# # 输出：1 -> 3 -> 2


import asyncio

#
# class AsyncDatabaseConnection:
#     async def __aenter__(self):  # 注意是 async def
#         print("1. [异步] 正在等待网络握手...")
#         await asyncio.sleep(1)  # 模拟异步 IO 等待
#         print("2. [异步] 数据库连接成功")
#         return "连接对象"
#
#     async def __aexit__(self, exc_type, exc_val, exc_tb):
#         print("3. [异步] 正在异步关闭连接，释放资源...")
#         await asyncio.sleep(0.5)  # 模拟异步关闭等待
#         print("4. [异步] 连接已关闭")
#
#
# # 使用（必须放在异步函数中）
# async def main():
#     async with AsyncDatabaseConnection() as conn:
#         print(f"5. 正在执行 SQL 查询，使用 {conn}")
#         # 即使这里报错，上面的 aexit 依然会等待执行完毕
#
#
# # 运行
# asyncio.run(main())

import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def AsyncDatabaseConnection():
    print("1. [异步] 正在连接远程服务器...")
    await asyncio.sleep(1)  # 开门需要等待
    try:
        yield "远程数据通道"  # 返回给 as 变量
    finally:
        print("2. [异步] 正在断开连接，清理缓存...")
        await asyncio.sleep(0.5)  # 关门也需要等待
        print("3. [异步] 已清理完毕")

async def main():
    async with AsyncDatabaseConnection() as chanl:
        print(f"4. 正在传输数据，使用 {chanl}")
        # 即使报错，finally 块依然会等关门执行完

asyncio.run(main())