# backend/config.py
# 全项目唯一的「配置中心」：从 .env.local 读取所有配置项，供任何模块取用。

from pydantic_settings import BaseSettings   # Pydantic 的「配置基类」，能自动从环境变量/.env 读取并做类型校验
from functools import lru_cache              # 标准库装饰器：缓存函数结果，让函数实际只执行一次
import os, sys
# 获取项目的根目录
live_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 获取 .env.local 文件的路径
env_local_path = os.path.join(live_path, ".env.local")
# print(f"env_local_path: {env_local_path}")

class Settings(BaseSettings):
    """配置模型：每个类属性对应 .env.local 里的一项配置。
    继承 BaseSettings 后，Pydantic 会自动把同名（大小写不敏感）的配置读进来并转成对应类型。"""

    # ── 数据库（PostgreSQL）──
    db_host: str = "localhost"   # 主机；写了默认值 = 可选项
    db_port: int = 5433          # 端口；本机 5432 已占用，隔离到 5433
    db_name: str = "eduagent"    # 库名
    db_user: str                 # 用户名；没有默认值 = 必填，.env.local 缺了会启动报错
    db_password: str             # 密码；同样必填

    @property
    def database_url(self) -> str:
        """把上面几个散件拼成 SQLAlchemy 需要的连接串。
        用 @property 装饰后，可像访问属性一样 settings.database_url 取值，不用加括号调用。"""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── Milvus 向量库 ──
    milvus_host: str = "localhost"
    milvus_port: int = 19531     # 本机 19530 已占用，隔离到 19531

    # ── 大模型（DeepSeek）──
    deepseek_api_key: str = ''   # 必填：DeepSeek 的 API Key
    deepseek_base_url: str = ""  # DeepSeek 接口地址
    deepseek_model_chat: str = ""              # 对话模型名
    deepseek_model_coder: str = ""            # 代码模型名

    # ── 意图路由（P1：本地 Ollama Qwen 优先 + 云端回退）──
    router_provider: str = "ollama_cpu"                 # ollama_cpu | ollama_gpu | dashscope | deepseek
    ollama_base_url: str = "http://localhost:11434"     # Ollama 原生 API 地址
    ollama_router_model: str = "qwen2.5:7b"
    router_timeout_seconds: int = 8
    dashscope_api_key: str = ""                         # 百炼（qwen-flash 回退通道）
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_router_model: str = "qwen-flash"

    # ── 本地模型权重路径 ──
    reranker_model_path: str = "./models/reranker/bge-reranker-large"    # 精排模型
    classifier_model_path: str = "./models/classifier/all-MiniLM-L6-v2"  # 意图分类模型
    bge_m3_model_path: str = "./models/embedding/bge-m3"                 # 嵌入模型
    finetuned_classifier_path: str="./models/classifier/finetune"

    # ── JWT 认证 ──
    jwt_secret_key: str                           # 必填：签发登录令牌用的密钥
    jwt_algorithm: str = "HS256"                  # 签名算法
    jwt_access_token_expire_minutes: int = 10080  # 令牌有效期（分钟）

    # ── MCP Server 地址（第五章用）──
    kb_mcp_server_url:  str = "http://localhost:8000/mcp/kb"
    web_search_mcp_url: str = "http://localhost:8000/mcp/web-search"
    cs_mcp_url:         str = "http://localhost:8000/mcp/cs"       # 客服订单工具 MCP（P2）
    mcp_api_key:        str = ""                                   # MCP 服务间鉴权 Key（空=不启用；.env.local 配置）

    # ── 订单数据源适配层（P2）：db=本地库直连 / api=外部订单系统 HTTP ──
    order_backend: str = "db"
    order_api_base: str = "http://localhost:8200"                  # mock_oms_api.py 演示服务
    order_api_timeout_seconds: int = 5

    # ── A2A RAG 知识库 Agent（P5）──
    rag_via_a2a: bool = False                      # 商品咨询检索是否走 A2A（演示开关）
    rag_agent_url: str = "http://localhost:5008"   # 独立 RAG Agent 地址
    rag_agent_port: int = 5008                     # 独立服务监听端口
    rag_agent_retrieval_mode: str = "mcp"          # mcp（默认）| inproc | http（B 后补预留）
    rag_external_url: str = ""                     # B 预留：一期 RAG 服务地址
    a2a_timeout_seconds: int = 3                   # A2A 超时（默认 3s，可按环境实测调整）

    # ── Redis（P6：缓存 / 写锁 / 指标）──
    redis_url: str = "redis://localhost:6380/0"

    # ── Web 搜索（Tavily 可选；留空则自动用免费的 DuckDuckGo）──
    tavily_api_key: str = ""

    # ── 应用基础配置 ──
    app_env: str = "local"                     # 运行环境标识
    app_debug: bool = False                    # 是否调试模式
    app_host: str = "0.0.0.0"                  # 监听地址
    app_port: int = 8000                       # 监听端口
    log_level: str = "INFO"                    # 日志级别
    default_tenant_id: str = "tenant_default"  # 多租户默认值

    class Config:
        """Pydantic 的元配置：告诉 BaseSettings 该怎么读取配置。"""
        env_file = env_local_path          # 从这个文件读取配置
        env_file_encoding = "utf-8"      # 文件编码
        case_sensitive = False           # 大小写不敏感：环境变量 DB_HOST 能对应字段 db_host
        extra = "ignore"                 # .env.local 里多出来的、模型没定义的字段一律忽略（不报错）


@lru_cache()       # laze                      # 缓存：保证 get_settings() 只创建一次 Settings、只读一次文件
def get_settings() -> Settings:
    """获取全局唯一的配置对象。任何模块要用配置，都调用这个函数。"""
    return Settings()                    # 首次调用时创建实例；之后每次都返回同一个缓存对象

config = Settings()
if __name__ == '__main__':

    print(Settings().db_user)
    # print(Settings().db_test)
    print(Settings().database_url)
    print(Settings().app_env)
    # settings = get_settings()
    # print(settings.database_url)
    # print(settings.deepseek_api_key)
    ...
