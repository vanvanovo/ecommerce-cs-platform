#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
两层 for 循环列表生成式（列表推导式）学习脚本
功能：演示如何从嵌套数据结构中提取数据，并生成新的字典列表。
"""

# ==================== 第一部分：模拟原始数据 ====================
# # 假设这是从内容评审系统中获取的维度评分数据
# dimension_scores = [
#     {"dimension": "技术能力", "issues": ["代码可读性差", "缺少单元测试"]},
#     {"dimension": "沟通协作", "issues": ["会议发言不积极"]},
#     {"dimension": "项目管理", "issues": []},  # 空列表，表示该维度没有问题
#     {"dimension": "学习能力", "issues": ["技术文档更新不及时"]}
# ]
#
# print("【原始数据结构】")
# for dim in dimension_scores:
#     print(f"维度：{dim['dimension']}，问题列表：{dim['issues']}")
# print("\n" + "=" * 50 + "\n")
#
#
# # ==================== 第二部分：你的原始代码（带详细拆解注释） ====================
# issues = [
#     # 1. 这是每次循环要生成的"元素"（一个字典）
#     {
#         "priority": "medium",                         # 固定字段
#         "dimension": dim["dimension"],                # 从外层循环变量 dim 中取值
#         "description": issue,                         # 从内层循环变量 issue 中取值
#         "location": "原文",                        # 固定字段
#         "suggestion": "请参考评审建议修改"             # 固定字段
#     }
#     # 2. 外层 for 循环：遍历 dimension_scores 列表中的每个字典，赋给变量 dim
#     for dim in dimension_scores
#     # 3. 内层 for 循环：遍历当前 dim 中 "issues" 键对应的列表，
#     #    将每个元素赋给变量 issue；若该列表为空，则内层循环不执行，自动跳过
#     for issue in dim.get("issues", [])
# ]
#
# print("【使用两层列表生成式生成的问题列表（你的原始写法）】")
# print(f"issues-->{issues}")
# # 漂亮的打印输出，方便查看结构
# for item in issues:
#     print(f"维度：{item['dimension']}，问题：{item['description']}")
# print(f"总共生成 {len(issues)} 条问题记录。")
# print("\n" + "=" * 50 + "\n")
#
#
# # ==================== 第三部分：等价的普通 for 循环写法（对比理解） ====================
# # 为了让你更直观地理解上述代码的执行流程，这里写出完全等价的普通循环版本
# issues_loop = []  # 创建一个空列表用于存放结果
#
# # 外层循环：遍历每个维度
# for dim in dimension_scores:
#     # 内层循环：遍历当前维度下的问题列表（如果为空，则循环体不执行）
#     for issue in dim.get("issues", []):
#         # 组装字典，添加到结果列表中
#         issues_loop.append({
#             "priority": "medium",
#             "dimension": dim["dimension"],
#             "description": issue,
#             "location": "原文",
#             "suggestion": "请参考评审建议修改"
#         })
#
# # 验证两种写法结果是否一致
# print("【验证：普通循环生成的结果是否与列表生成式一致？】")
# print(f"列表生成式结果：{issues}")
# print(f"普通循环结果：{issues_loop}")
# print(f"两者相等吗？ {issues == issues_loop}")  # 输出 True 表示完全一样
# print("\n" + "=" * 50 + "\n")


# ==================== 第四部分：最简两层循环示例（彻底搞懂执行顺序） ====================
# 抛开业务逻辑，用最简单的数字和字母展示两层 for 的执行顺序

colors = ['红', '蓝']
sizes = ['大', '中', '小']

# 普通循环写法
print("【普通嵌套循环执行顺序】")
for color in colors:          # 外层先固定 '红'
    for size in sizes:        # 内层遍历 '大','中','小'
        print(f"{color}{size}", end=" ")  # 输出：红大 红中 红小
    # 外层换到 '蓝'，内层再次遍历 '大','中','小'
print("\n")  # 换行
#
# # 列表生成式写法（完全等价）
combined = [f"{color}{size}" for color in colors for size in sizes]
# print("【列表生成式执行结果】")
print(combined)  # 输出：['红大', '红中', '红小', '蓝大', '蓝中', '蓝小']
print("\n" + "=" * 50 + "\n")
#
#
# # ==================== 第五部分：附加技巧——带过滤条件的多层推导 ====================
# # 如果你只想保留问题描述长度大于 4 的问题（例如过滤掉过短的无效内容）
#
# filtered_issues = [
#     {
#         "dimension": dim["dimension"],
#         "issue_text": issue
#     }
#     for dim in dimension_scores
#     for issue in dim.get("issues", [])
#     if len(issue) > 4  # 过滤条件：只保留长度大于4的问题描述
# ]
#
# print("【带过滤条件的结果（只保留长度 > 4 的问题）】")
# print(filtered_issues)
# # 预期输出：只保留 '代码可读性差'(6个字) 和 '技术文档更新不及时'(8个字)，
# # '缺少单元测试'(5个字) 也满足，'会议发言不积极'(6个字) 也满足，都会保留。
# # 若想测试过滤，可以修改条件，例如 len(issue) > 6 则只会保留 '技术文档更新不及时'