blocks = [(434,811,523,828,"你好", 0, 0),
          (123,411,343,628,"不是", 0, 0),
          (455,1021,456,768,"你好", 0, 0)]

result = sorted(blocks, key=lambda b: b[1])
print(result)

blocks.sort(key=lambda b: b[1])
print(blocks)
#
# issues = [{'priority': 'low', 'dimension': '真实可信度2'},
#           {'priority': 'high', 'dimension': '真实可信度1'},
#           {'dimension': '真实可信度1'},
#           {'priority': 'medium', 'dimension': '真实可信度3'},
#           {'priority': 'high', 'dimension': '真实可信度4'}]
# priority_order = {"high": 0, "medium": 1, "low": 2}  # 按优先级排序
# issues.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
# print(issues)


# all_raw_issues = ["问题1","问题2", "问题3"]
# a = (f"- {i}" for i in all_raw_issues)
# print(a)
# print('\n'.join(a))