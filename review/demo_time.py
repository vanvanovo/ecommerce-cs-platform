# from datetime import datetime, timezone
# import time
#
# last_ts = datetime.now(timezone.utc)
# print(last_ts)
# time.sleep(1.5)  # 模拟代码运行等了 1.5 秒
#
# elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
#
# print(elapsed)
# 输出：1.500123  （因为有代码执行开销，会略大于 1.5）
# 注意：这是一个浮点数，比如 1.500123

from datetime import datetime, timezone, timedelta

# 北京时间 08:00
beijing_tz = timezone(timedelta(hours=8))
t1 = datetime(2026, 7, 5, 8, 0, 0, tzinfo=beijing_tz)
print(t1)

# 同一时刻的 UTC 时间 00:00
t2 = datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc)
print(t2)

# 直接相减，结果为 0，证明 Python 自动转化了
print(t1 - t2)  # 输出 0:00:00

# 或者直观地看转化后的秒数是否相等
print(t1.timestamp())
print(t2.timestamp())