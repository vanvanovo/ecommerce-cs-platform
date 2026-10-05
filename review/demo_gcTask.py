# import asyncio
# import os
# import tempfile
# import functools
#
# _background_tasks: set[asyncio.Task] = set()
#
# async def _mark_review_failed(review_id, msg):
#     print(f"  [DB] 写入失败状态 → review_id={review_id}, msg={msg}")
#
# review_id = "R-001"
# tmp_path = os.path.join(tempfile.gettempdir(), f"{review_id}_upload.pdf")
# print(f'tmp_path={tmp_path}')
# file_bytes = b"fake pdf content"
# with open(tmp_path, "wb") as f:
#     f.write(file_bytes)
# print(f"  [准备] 临时文件已创建: {tmp_path}")
# def _on_task_done(t: asyncio.Task):
#     _background_tasks.discard(t)
#
#     if os.path.exists(tmp_path):
#         os.remove(tmp_path)
#         print(f"  [清理] 临时文件已删除: {tmp_path}")
#
#     mark_failed_msg = None
#
#     if t.cancelled():
#         mark_failed_msg = "审查任务被服务重启中断，请重试。"
#         print(f"  [回调] 任务被取消")
#     else:
#         exc = t.exception()
#         if exc:
#             mark_failed_msg = f"审查任务执行失败：{exc}"
#             print(f"  [回调] 任务抛出异常: {exc}")
#         else:
#             print(f"  [回调] 任务正常完成，结果: {t.result()}")
#
#     if mark_failed_msg:
#         try:
#             loop = asyncio.get_running_loop()
#             loop.create_task(_mark_review_failed(review_id, mark_failed_msg))
#         except RuntimeError:
#             pass
#
# async def task_success():
#     await asyncio.sleep(0.1)
#     return "审查结果：评分 85 分"
#
# async def task_exception():
#     await asyncio.sleep(0.1)
#     raise ValueError("PDF 解析失败，文件损坏")
#
# async def task_cancel():
#     await asyncio.sleep(10)
#     return "不会跑到这里"
#
#
# async def main():
#     # ── 情况1：正常完成 ──
#     # print("=" * 40)
#     # print("【情况1】正常完成")
#     # t1 = asyncio.create_task(task_success())
#     # _background_tasks.add(t1)
#     # t1.add_done_callback(_on_task_done)
#     # await asyncio.sleep(0.5)
#
#     # # ── 情况2：任务抛异常 ──
#     # print("=" * 40)
#     # print("【情况2】任务抛出异常")
#     # t2 = asyncio.create_task(task_exception())
#     # _background_tasks.add(t2)
#     # t2.add_done_callback(_on_task_done)
#     # await asyncio.sleep(0.5)
#     #
#     # # ── 情况3：任务被取消 ──
#     print("=" * 40)
#     print("【情况3】任务被取消")
#     t3 = asyncio.create_task(task_cancel())
#     _background_tasks.add(t3)
#     t3.add_done_callback(_on_task_done)
#     await asyncio.sleep(0.1)
#     t3.cancel()
#     await asyncio.sleep(0.5)
#     #
#     print("=" * 40)
#     print("剩余后台任务数：", len(_background_tasks))
#
# asyncio.run(main())



import asyncio

_background_tasks: set[asyncio.Task] = set()

# 模拟耗时的后台任务（比如批改试卷）
async def grade_exam(exam_id: str):
    print(f"  [后台] 开始批改 {exam_id}...")
    await asyncio.sleep(3)          # 模拟耗时3秒
    print(f"  [后台] {exam_id} 批改完成！")

# 协程函数：立即返回，后台默默跑
async def submit_exam(exam_id: str) -> dict:
    task = asyncio.create_task(grade_exam(exam_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"exam_id": exam_id, "status": "processing", "message": "已提交，正在后台批改"}

async def main():
    print("【提交试卷】")
    result = await submit_exam("EX-001")

    # 立即拿到返回值，后台任务还在跑
    print(f"【立即返回】{result}")
    print(f"【此刻后台任务数】{len(_background_tasks)}")

    print("【主流程继续做其他事情...】")
    await asyncio.sleep(4)          # 等后台跑完

    print(f"【最终后台任务数】{len(_background_tasks)}")

asyncio.run(main())