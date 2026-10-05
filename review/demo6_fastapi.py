from  fastapi import FastAPI,Depends,UploadFile,File,HTTPException
import uvicorn
"""第一个实例应用
    restful 规范: GET(查) POST(增) PUT(改) DELETE(删)
"""
# 创建 FastAPI 应用实例
app =  FastAPI(title="EduAgent Demo")

# 编写路由处理函数
@app.get("/health")
async def health_check():
    return {"status":"ok123"}


"""
    Pydantic 获取请求体
    当前端要「提交数据」（比如登录时提交用户名密码），
    我们用一个 Pydantic 模型作为接口函数的参数。FastAPI 会自动把请求体里的 JSON 解析成这个模型，并完成校验：
"""
from pydantic import BaseModel,Field
# 请求体模型
class LoginRequst(BaseModel):
    username: str = Field(...,description="用户名或邮箱") # ...表示参数为必填
    password: str = Field(...,description="密码")
# 响应模型
class TokenResponse(BaseModel):
    access_token: str
    token_type  : str = "bearer"
    role:         str

@app.post("/login", response_model=TokenResponse)
async def login(req: LoginRequst):           # 参数类型是 Pydantic 模型
    # req 已经是解析并校验好的对象，直接用 req.username / req.password
    if req.username == "student01" and req.password == "Student@123456":
        return TokenResponse(access_token="fake-token-abc", role="student")
    return {"access_token": "", "token_type": "bearer", "role": "guest"}

"""
     路径参数与查询参数
     路径参数——把参数嵌在 URL 路径里，用 {} 占位，函数里同名参数自动接收
     查询参数——URL 问号后面的 ?key=value，在函数里写成「带默认值的普通参数」：
"""
@app.get("/reviews/{review_id}")
async def get_review(review_id: str):
    return {"review_id": review_id, "status": "completed"}
# 访问 GET /reviews/abc-123 → review_id 自动等于 "abc-123"

@app.get("/reviews")
async def list_reviews(page: int = 1, size: int = 10):
    return {"page": page, "size": size}
# 访问 GET /reviews?page=2&size=20 → page=2, size=20
# 不传则用默认值 page=1, size=10


"""
     依赖注入 Depends
     很多接口都需要做一些**相同的前置工作**：拿一个数据库连接、校验用户有没有登录……如果在每个接口里都重复写这些，
     既啰嗦又难维护。FastAPI 用**依赖注入（Depends）**优雅地解决了这个问题：
     
     把「通用的前置逻辑」写成一个函数（叫「依赖」），在接口参数里用 Depends(依赖函数) 声明一下，
     FastAPI 就会在执行接口前**自动先跑这个依赖、把结果喂给接口。
"""
async def get_db():
    return {"db","fake_session"}
async def get_current_user():
    return {"userid":"test_user","role":"student"}
@app.get("/my_reviews")
async def my_reviews(
        db=Depends(get_db),
        current_user=Depends(get_current_user)
):
    return {"db":db,"current_user":current_user}


@app.post("/upload", status_code=202)  # 202表示接收成功，但未处理完成
async def upload(file: UploadFile = File(...)):
    content = await file.read()                  # 异步读取文件内容（bytes）
    return {"filename": file.filename, "size": len(content)}


from sse_starlette.sse import EventSourceResponse
import asyncio
import json
@app.post("/chat/stream")
async def chat_stream():
    async def event_generator():
        answer = "装饰器是一种包装函数的语法。"
        for char in answer:                       # 模拟逐字生成
            await asyncio.sleep(0.1)
            # 每个事件是一个字典，data 里放 JSON 字符串
            yield {"data": json.dumps({"type": "token", "content": char},ensure_ascii=False)}
        yield {"data": json.dumps({"type": "done"})}   # 结束标志

    return EventSourceResponse(event_generator())

def find_review(review_id: str):
    pass

@app.get("/reviews2/{review_id}")
async def get_review(review_id: str):
    review = find_review(review_id)     # 伪代码
    if review is None:
        raise HTTPException(status_code=404, detail="审查记录不存在")
    return review

if __name__ == "__main__":
    # 启动应用
    uvicorn.run(app,host="0.0.0.0",port=4000)