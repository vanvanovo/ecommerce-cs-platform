# backend/api/router.py
# API 路由总入口

from fastapi import APIRouter
from backend.api.v1 import auth, qa, unified_chat, order, aftersale, complaint, console  # 子模块

api_router = APIRouter()                              # 总路由

# 把每个子 router 带前缀 + 标签聚合进来
api_router.include_router(auth.router,          prefix="/auth",      tags=["认证"])
api_router.include_router(unified_chat.router,  prefix="/chat",      tags=["AI助手"])   # 本章统一入口
api_router.include_router(qa.router,            prefix="/qa",        tags=["智能问答"])  # 第 5 章
api_router.include_router(order.router,         prefix="/order",     tags=["订单物流"])  # P3
api_router.include_router(aftersale.router,     prefix="/aftersale", tags=["售后工单"])  # P3
api_router.include_router(complaint.router,     prefix="/complaint", tags=["投诉安抚"])  # P3
api_router.include_router(console.router,       prefix="/console",   tags=["运营台"])   # P6