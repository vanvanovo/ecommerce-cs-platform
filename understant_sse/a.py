# import uvicorn
# from fastapi import FastAPI
#
# app = FastAPI()
#
#
# @app.get("/chat")
# async def chat():
#
#     return {
#         "answer": "你好，我是AI助手"
#     }
# if __name__ == '__main__':
#     uvicorn.run(app, host='0.0.0.0', port=8009)


import asyncio


async def fake_graph():

    yield {
        "event": "on_chain_start",
        "node": "retrieve"
    }

    await asyncio.sleep(1)

    yield {
        "event": "on_chat_model_stream",
        "content": "Spring"
    }

    yield {
        "event": "on_chat_model_stream",
        "content": " IOC"
    }

    yield {
        "event": "on_chat_model_stream",
        "content": "（控制反转）"
    }

    yield {
        "event": "on_chain_end",
        "answer_mode": "rag"
    }

async def main():
    async for event in fake_graph():
        print(event)
        print("*"*50)

import asyncio
asyncio.run(main())

