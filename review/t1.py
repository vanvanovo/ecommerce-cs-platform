# 暂存到临时目录
import tempfile
import os

print(tempfile.gettempdir())
tmp_path = os.path.join(tempfile.gettempdir(), f"{123}_upload.pdf")
print(tmp_path)