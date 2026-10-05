from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

app = FastAPI()
import asyncio


async def fake_llm():

    yield {
        "type": "progress",
        "msg": "开始思考"
    }

    await asyncio.sleep(1)

    for ch in "你好AI":

        yield {
            "type": "token",
            "content": ch
        }

        await asyncio.sleep(0.2)

    yield {
        "type": "done"
    }


import json



@app.get("/stream")
async def stream():

    async def event_generator():

        async for event in fake_llm():

            yield {
                "data": json.dumps(
                    event,
                    ensure_ascii=False
                )
            }

    return EventSourceResponse(
        event_generator()
    )
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
#
# # async def fake_graph():
# #
# #     yield {
# #         "event":"on_chain_start",
# #         "node":"retrieve"
# #     }
# #
# #     yield {
# #         "event":"on_chat_model_stream",
# #         "content":"Spring"
# #     }
# #
# #     yield {
# #         "event":"on_chat_model_stream",
# #         "content":" IOC"
# #     }
# #
# #     yield {
# #         "event":"on_chain_end",
# #         "answer_mode":"rag",
# #         "confidence":0.92
# #     }
# #
# # async def event_generator():
# #
# #     async for event in fake_graph():
# #
# #         if event["event"] == "on_chain_start":
# #
# #             yield {
# #                 "data": json.dumps({
# #                     "type":"progress",
# #                     "stage":"检索知识库"
# #                 })
# #             }
# #
# #         elif event["event"] == "on_chat_model_stream":
# #
# #             yield {
# #                 "data": json.dumps({
# #                     "type":"token",
# #                     "content":event["content"]
# #                 })
# #             }
# #
# #         elif event["event"] == "on_chain_end":
# #
# #             yield {
# #                 "data": json.dumps({
# #                     "type":"meta",
# #                     "answer_mode":event["answer_mode"],
# #                     "confidence":event["confidence"]
# #                 })
# #             }
# #
# #             yield {
# #                 "data": json.dumps({
# #                     "type":"done"
# #                 })
# #             }
