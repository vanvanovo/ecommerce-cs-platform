
# 文本块的blocks [42,53,4]
a =  [(12,5, 12, 3, '佟昇', 0, 0),
      (1, 1, 44, 33, '17888372960@163.com 17888372960', 1, 0),
      (42, 6, 12, 43, '意向岗位：大模型应用开发工程师', 2, 0)]

# 按照y坐标排序,符合文本块从上到下的顺序
sorted_blocks = sorted(a, key=lambda b: b[1])
print(sorted_blocks)
b = (b[4].strip() for b in sorted_blocks if b[4].strip())
# print(list(b))
page_text = "\n".join(b)
print(page_text)