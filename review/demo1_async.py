"""异步函数中跑耗时比较长的同步任务"""
import asyncio
import time
#
# def heavy_sync_work(n):  # 模型推理
#     print("同步阻塞开始")
#     time.sleep(2)
#     print("同步阻塞阻塞")
#     return n*n
#
# async def main():
#     loop = asyncio.get_running_loop() # 拿到当前事件循环
#     # 在事件循环中运行同步函数  ,同步函数会创建一个线程池来运行
#     # parma1： 线程池句柄 parma2： 同步函数, param3: 函数参数
#     result = await  loop.run_in_executor(None,heavy_sync_work,10) # 让出cpu
#     print("结果：",result)
#
# asyncio.run(main())

"""异步函数如何实现并发"""
#
# async  def fetch(name,sec):
#     print(f"开始 {name}")
#     # time.sleep(sec)
#     await asyncio.sleep(sec)
#     print(f"完成 {name}")
#     return f"{name} 的结果"
#
# async def main():
#
#    # await  fetch("请求A",2)
#    # await  fetch("请求B", 2)
#    # await  fetch("请求C", 2)
#
#    results = await asyncio.gather(
#        fetch("请求A", 2),
#        fetch("请求B", 2),
#        fetch("请求C", 2)
#    )
#    print(results)
#
# asyncio.run(main())

import asyncio
# 模块级集合：持有所有后台任务的强引用，防止被 GC 提前回收
_background_tasks: set[asyncio.Task] = set()

async def grade_exam(exam_id):
    print(f"开始批改试卷 {exam_id}……")
    await asyncio.sleep(2)               # 模拟耗时的批改过程
    print(f"试卷 {exam_id} 批改完成")

async def submit():
    task = asyncio.create_task(grade_exam("EX-001"))  # 丢到后台
    _background_tasks.add(task)                         # 关键①：强引用，防 GC
    # _background_tasks.discard 集合移除对象的函数
    # 任务执行完成之后会自动进入到_background_tasks.discard函数去，参数为该任务的句柄  _background_tasks.discard(task)
    task.add_done_callback(_background_tasks.discard)   # 关键②：跑完自动移除
    print("接口立即返回：已收到，正在后台批改")

async def main():
    await submit() # 不耗时任务
    await asyncio.sleep(1)    # 模拟服务持续运行，给后台任务跑完的时间
    print("当前后台任务数：", len(_background_tasks))

asyncio.run(main())

# s1 = {12,34,63}
# print(s1)
# s1.discard(34)
# print(s1)