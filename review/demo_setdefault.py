# 原始数据（每行是个字典）
rows = [
    {"label": "fruit", "item": "apple"},
    {"label": "fruit", "item": "banana"},
    {"label": "vegetable", "item": "carrot"},
    {"label": "fruit", "item": "orange"},
    {"label": "vegetable", "item": "broccoli"},
]

buckets = {}  # 空字典，用来分组

for row in rows:
    label = row["label"]
    # print(f'label: {label}')
    # 确保 buckets 中有 label 这个键，且值为列表
    buckets.setdefault(label, [])  # 如果 label 不存在，插入空列表
    # print(f"buckets: {buckets}")
    buckets[label].append(row["item"])  # 现在可以安全地 append

print(buckets)
'''
buckets.setdefault(label, []) 执行后：

第一次遇到 "fruit" 时，buckets 中没有这个键，于是插入 "fruit": []，并返回这个空列表。

第二次遇到 "fruit" 时，键已经存在，直接返回已有的列表（不改变它）。

接着 buckets[label].append(...) 就把元素追加到对应的列表里。

这样就不需要先判断 if label not in buckets 再创建列表，一行搞定。
'''
# buckets1 = {}
# for row in rows:
#     buckets1.setdefault(row["label"], []).append(row["item"])
#
# print(buckets1)