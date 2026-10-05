from pathlib import Path
# pathlib.Path 是 Python 3.4+ 开始推荐的面向对象的文件路径处理方式，比传统的 os.path 更直观、更优雅。
# 1. 创建路径对象（支持 / 拼接，超级方便）
# p = Path("/Users/ligang/Desktop/LiveEduAgent") / "dm_projects" / "data.csv"
# print(f"路径: {p}")
#
# # 2. 提取文件名、后缀、纯文件名（你的代码核心）
# print(f"完整文件名: {p.name}")      # data.csv
# print(f"后缀: {p.suffix}")          # .csv
# print(f"纯文件名(无后缀): {p.stem}") # data  <--- 这就是你代码里用的
#
# # 3. 获取父目录
# print(f"父目录: {p.parent}")         # /home/user/projects
#
# # 4. 判断文件/目录是否存在
# print(f"存在吗? {p.exists()}")
#
# # 5. 判断是文件还是文件夹
# print(f"是文件吗? {p.is_file()}")    # True (如果存在且是文件)
# print(f"是目录吗? {p.is_dir()}")     # False
#
# # 6. 创建目录（自动创建父级，不怕报错）
new_dir = Path("./my_output/logs")
new_dir.mkdir(parents=True, exist_ok=True)  # parents=True 自动建父级，exist_ok=True 有则忽略
print(f"目录已创建: {new_dir}")

# 7. 读写文本文件（一步到位，不用再 open close）
file_path = Path("./my_output/hello.txt")
file_path.write_text("Hello World!", encoding="utf-8")  # 写
content = file_path.read_text(encoding="utf-8")         # 读
print(f"读取内容: {content}")