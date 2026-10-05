# -*-coding:utf-8-*-
import asyncio
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

llm = init_chat_model(
    model="deepseek-v4-flash",  # 模型id
    model_provider="openai",  # 模型通信协议
    api_key = "sk-xxxx",
    base_url="https://api.deepseek.com/",
    temperature=0,  # 不要随意发挥
    extra_body = {'thinking':{"type":"disabled"}} # 关闭模型思考能力
)

# async def main():
#     messages = [
#         SystemMessage(content="你是一位专业的 Python 讲师，用一句话回答。"),
#         HumanMessage(content="什么是装饰器？"),
#     ]
#     response =  await llm.ainvoke(messages)    # 异步调用，返回一个 AIMessage
#     print(response.content)                       # 用 .text 取出文本（属性，不加括号！）
#     print("*" * 80)
#     print(response.text)                       # 用 .text 取出文本（属性，不加括号！）
#
# asyncio.run(main())

from pydantic import BaseModel, Field

# ① 定义期望的输出结构（回顾 2.2：description 就是给大模型的填空指令）
class PersonInfo(BaseModel):
    name: str = Field(description="姓名")
    age:  int = Field(description="年龄（整数）")
    city: str = Field(description="所在城市")
#
# ② 把模型绑定上去，得到一个「结构化输出版」的 llm
structured_llm = llm.with_structured_output(PersonInfo, method="function_calling")

async def main():
    messages = [
        SystemMessage(content="你负责从文本中抽取人物信息。"),
        HumanMessage(content="我叫小明，今年 25 岁，住在上海。"),
    ]
    # ③ 调用后直接返回 PersonInfo 对象，不是文本！
    result: PersonInfo = await structured_llm.ainvoke(messages)
    print(result.model_dump()) # 将返回对象的字典格式
    print(type(result))      # <class '__main__.PersonInfo'>
    print("*"*80)
    print(result.name)       # 小明
    print(result.age)        # 25
    print(result.city)       # 上海

asyncio.run(main())


# steam输出
async def main():
    messages = [HumanMessage(content="用三句话介绍一下 Python。")]
    async for chunk in llm.astream(messages):   # 逐token输出
        print(chunk.text, flush=True,end='')    # 拼接打印，形成打字机效果

asyncio.run(main())
