"""
    装饰器： 在不修改原函数情况下，给函数增加功能

    应用场景：
        1、记录时间
        2、日志记录
        3、异常处理
        4、权限控制
"""
import time

def pay():
    time.sleep(2)
    print("用户支付成功")

# 在不修改原函数情况下，给函数增加记录时间功能
"""方法1：在函数前后增加代码来添加功能"""
# xxx1行处
# ntime = time.time()
# pay()
# print("程序的花费时间:",time.time()-ntime)
#
# # xxx2行处
# ntime = time.time()
# pay()
# print("程序的花费时间:",time.time()-ntime)

# 缺点：函数出现在多个地方会导致代码冗余

"""方法2：通过对接口封装一个函数"""
# def wrapper():
#     ntime = time.time()
#     pay()
#     print("程序的花费时间:", time.time() - ntime)

# xxx1行处
# wrapper()

# xxx2行处
# wrapper()

def recharge(num):
    print("开始充电")
    time.sleep(3)
    print("充电完成")
    return num

# 缺点 ： 每个函数如果要加入功能都需要重新封装
# recharge(12)
"""方法3：只需要通过一个装饰函数就可以实现装饰其他函数"""
def wrapper(*args, **kwargs):
    ntime = time.time()
    ret = func(*args,**kwargs)
    print("程序的花费时间:", time.time() - ntime)
    return ret

# 装饰pay接口
# func = pay
# print(wrapper())

# 装饰pay接口
# func = recharge
# print(wrapper(num=12))


# 如何不修改函数名也能加功能
# func = recharge
# recharge = wrapper
# recharge(num=12)

# func = pay
# pay = wrapper
# pay()

"""整合上面的方法 """
from functools import wraps
# # 无参装饰器 嵌套函数
def outer(func):
    @wraps(func) #  warpper.__name__ =  func.__name__ warpper.__doc__ =  func.__doc__
    def warpper(*args,**kwargs):
        ntime = time.time()
        ret = func(*args, **kwargs)
        print("程序的花费时间:", time.time() - ntime)
        return ret
    return warpper

@outer
def pay(): # func = pay, pay = wraper
    """支付接口"""
    time.sleep(2)
    print("用户支付成功")
@outer
def recharge(num):
    print("开始充电")
    time.sleep(3)
    print("充电完成")
    return num

print(pay.__name__) # 输出函数名
print(pay.__doc__) # 输出函数名

# print(recharge(10))

"""无参装饰器模板"""
# def outer(func):
#     def warpper(*args,**kwargs):
#         # 函数加功能的地方
#         ret = func(*args, **kwargs)
#         # 函数加功能的地方
#         return ret
#     return warpper


