from pydantic import BaseModel

# class Student(BaseModel):
#     name: str          # 字符串
#     age: int           # 整数
#
# # 用关键字参数创建实例
# s = Student(name="小明", age=18)
# # s = Student(name="小明", age="十八")
# print(s.name)          # 小明
# print(s.age)           # 18
# print(type(s.age))           # 18
# print(s)               # name='小明' age=18

# from pydantic import BaseModel, Field
#
# class UserProfile(BaseModel):
#     name:  str = Field(description="用户姓名")            # 必填：没有默认值
#     phone: str = Field(default="", description="手机号")  # 可选：有默认值 ""
#     age:   int = Field(default=18, description="年龄")    # 可选：默认 18
#     # tags:  list[str] = Field(default_factory=list, description="标签列表")  # 正确写法：只能列表中存字符串
#     tags:  list[str | int] = Field(default_factory=list, description="标签列表")  # 正确写法:列表中既可以是字符串也可以是整数
#     title: str = "这是一个学生的介绍" # 简化默认值的写法
#
#
# up = UserProfile(name="张三", phone="123456", tags=["a", 2, "c"])
# print(up)
# print(up.name)
# print(up.age)
# print(up.phone)
# print(up.tags)
# print(up.title)
# print(up.g1)
#
# from pydantic import BaseModel, Field
# from typing import Optional
# class EducationItem(BaseModel):
#     school: str = Field(description="学校名称")
#     major:  str = Field(description="专业名称")
#
# class Resume(BaseModel):
#     name:      str                = Field(description="姓名")
#     education: list[EducationItem] = Field(default_factory=list)  # 教育经历列表
#     nickname: Optional[str] = None  # 可以是字符串，也可以是 None
#
# # 创建时，嵌套部分可以直接用字典，Pydantic 会自动转成对应的子模型
# # resume = Resume(
# #     name="小明",
# #     education=[
# #         {"school": "清华大学", "major": "计算机"},
# #         {"school": "北京大学", "major": "软件工程"},
# #     ],
# # )
#
# resume = Resume(
#     name="小明",
#     education=[EducationItem(school="清华大学", major="计算机"),
#                EducationItem(school="清华大学", major="计算机")],
# )
#
#
# print(f'resume: {resume}')
# print("*"*80)
# print(resume.name)                    # 小明
# print(resume.education[0].school)     # 清华大学  ← 注意：已经是 EducationItem 对象了
# print(type(resume.education[0]))      # <class '__main__.EducationItem'>
# print(resume.nickname)      # <class '__main__.EducationItem'>

from pydantic import BaseModel, Field

# class Student(BaseModel):
#     name: str = Field(description="姓名")
#     age:  int = Field(default=18, description="年龄")
#
# s = Student(name="小明", age=20)
#
# d = s.model_dump()       # 模型 → 字典
# # d = s.dict()
# print(d)                 # {'name': '小明', 'age': 20}
# print(type(d))           # <class 'dict'>
#
# data = {"name": "小红", "age": 22}
# s2 = Student(**data)     # 字典 → 模型
# print(s2.name)           # 小红


from enum import Enum

class InterviewStage(str, Enum):       # 继承 str，取值就是字符串
    WARMUP    = "warmup"
    TECH_BASE = "tech_base"
    PROJECT   = "project"
    CLOSING   = "closing"
    FINISHED  = "finished"

print(InterviewStage.WARMUP)           # InterviewStage.WARMUP
print(InterviewStage.WARMUP.value)     # warmup
if InterviewStage.WARMUP == "warmup":
    print("这是预热阶段")
if InterviewStage.PROJECT == "project":
    print("项目阶段")



