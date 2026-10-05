"""
三级嵌套结构化输出示例
证明：只需传最外层 Schema，嵌套结构自动展开提取

嵌套层级：
  Company（第一层）
    └── Department（第二层）
          └── Employee（第三层）
"""

from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

llm = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key="sk-xxxx",
    base_url="https://api.deepseek.com/v1",
    temperature=0,
)
from typing import Optional


# ============================================================
# 第三层：员工
# ============================================================
class Employee(BaseModel):
    """第三层：单个员工"""
    name:       str           = Field(description="员工姓名")
    title:      str           = Field(description="职位名称")
    years:      int           = Field(description="工作年限")
    email:      Optional[str] = Field(default=None, description="邮箱，没有则为null")


# ============================================================
# 第二层：部门（包含多个 Employee）
# ============================================================
class Department(BaseModel):
    """第二层：部门，内含员工列表"""
    dept_name:  str            = Field(description="部门名称")
    budget:     float          = Field(description="部门年度预算，单位万元")
    employees:  list[Employee] = Field(default_factory=list, description="部门员工列表")


# ============================================================
# 第一层：公司（包含多个 Department）
# ============================================================
class Company(BaseModel):
    """第一层：公司，内含部门列表"""
    company_name: str             = Field(description="公司名称")
    industry:     str             = Field(description="所属行业")
    founded_year: int             = Field(description="成立年份")
    departments:  list[Department] = Field(default_factory=list, description="部门列表")


# ============================================================
# 初始化 DeepSeek 模型（兼容 OpenAI 接口）
# ============================================================

# ============================================================
# 关键：只传最外层 Company，嵌套全部自动展开
# ============================================================
structured_llm = llm.with_structured_output(Company,method="function_calling")  # ← 只传这一个！


# ============================================================
# 模拟一段"非结构化的公司介绍文本"
# ============================================================
text = """
未来科技有限公司成立于2015年，专注于人工智能行业。

公司目前有两个部门：

【研发部门】
年度预算 500 万元，共有两名员工：
- 张伟，职位是算法工程师，工作了 5 年，邮箱 zhangwei@future.com
- 李娜，职位是产品经理，工作了 3 年，暂无邮箱

【市场部门】
年度预算 200 万元，共有一名员工：
- 王磊，职位是市场总监，工作了 8 年，邮箱 wanglei@future.com
"""


# ============================================================
# 调用：直接传文本，模型自动按三层结构提取
# ============================================================
result: Company = structured_llm.invoke([HumanMessage(content=text)])

print(f'result: {result}')
print("=" * 50)
print(f'result: {result.model_dump()}')
# ============================================================
# 打印结果，验证三层嵌套都被正确提取
# ============================================================
print("=" * 50)
# print(f"公司名称：{result.company_name}")
# print(f"所属行业：{result.industry}")
# print(f"成立年份：{result.founded_year}")
# print(f"部门数量：{len(result.departments)}")
#
# for dept in result.departments:
#     print(f"\n  【{dept.dept_name}】预算：{dept.budget} 万元")
#     for emp in dept.employees:
#         print(f"    - {emp.name} | {emp.title} | {emp.years}年 | 邮箱：{emp.email}")
#
# print("=" * 50)
# print("\n✅ 结论：只传了最外层 Company，三层嵌套全部自动提取成功！")