
# sorted([23,23,6,1,5])
a = [(12, 43, 12, 11, '佟昇', 0, 0),
    (3, 4, 12, 23, '17888372960@163.com 17888372960 ', 1, 0),
    (42, 1, 3, 6, '教育经历\n', 3, 0)
    ]
sorted_blocks = sorted(a, key=lambda b: b[1])
print(sorted_blocks)
page_text = "\n".join(b[4].strip() for b in sorted_blocks if b[4].strip())
print(page_text)
# all_text_parts.append(page_text)