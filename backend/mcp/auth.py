# backend/mcp/auth.py
# MCP 子应用鉴权：X-MCP-Key 校验（服务间调用身份）
#
# 背景：
#   - mount 的子应用不共享父应用中间件（JWT/CORS 等不会自动生效），
#     因此鉴权必须包裹在 MCP ASGI 子应用外层；
#   - MCP_API_KEY 未配置时自动放行（本地开发方便）；配置后强制校验；
#   - 未通过时返回 JSON-RPC 风格的 401，便于 MCP 客户端识别。

import json


class ApiKeyAuthMiddleware:
    """ASGI 中间件：校验请求头 X-MCP-Key 是否等于配置的 MCP_API_KEY。"""

    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = (api_key or "").strip()

    async def __call__(self, scope, receive, send):
        # 非 HTTP（如 lifespan）直接放行；未配置 Key 时放行（开发模式）
        if scope.get("type") != "http" or not self.api_key:
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        if headers.get("x-mcp-key") == self.api_key:
            await self.app(scope, receive, send)
            return

        body = json.dumps({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32001, "message": "Unauthorized: missing or invalid X-MCP-Key"},
        }, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
