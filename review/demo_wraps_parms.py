"""
带参装饰器模板：
    def g_outer(x):
        def outer(func):
            def wrapper(*args, **kwargs):
                res = func(*args, **kwargs)
                return res
            return wrapper
        return outer
带参装饰器模板：@装饰器函数名(参数)，根据参数不同，装饰不同功能
"""
import time
from functools import wraps
# 权限验证带参装饰器
def auth(source):
    def outer(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if source == 'file':
                user =  input("user>> ")
                pwd  =  input("pwd>> ")
                if user =='12345' and pwd =='12345':
                    res = func(*args, **kwargs)
                else:
                    res = None
            elif source == 'mysql':
                res = func(*args, **kwargs)
                print("基于mysql的登录验证")
            return res
        return wrapper
    return outer


@auth('file')  # outer =  auth('file')  home =  outer(home)
def home():
    """主页面"""
    time.sleep(1)
    print("welcome to home!")

print(home.__name__)
print(home.__doc__)