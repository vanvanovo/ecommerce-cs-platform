def build_filter(tenant_id: str, course_id=None):
    safe_tenant = tenant_id.replace('"', '\\"')
    print(f'safe_tenant: {safe_tenant}')
    expr = f'tenant_id == "{safe_tenant}"'
    if course_id:
        safe_course = course_id.replace('"', '\\"')
        print(f'safe_course: {safe_course}')
        expr += f' and course_id == "{safe_course}"'
    return expr

# 例子 1：正常值（看不出变化）
print("【例1】正常值")
print("输入 tenant=abc, course=123")
print("输出:", build_filter("abc", "123"))
print("-" * 40)
#
# 例子 2：值里面带了双引号（重点看转义效果）
print("【例2】tenant 里带双引号")
print('输入 tenant=te"nt, course=co"urse')
print("输出:", build_filter('te"nt', 'co"urse'))
print("-" * 40)

# 例子 3：恶意注入尝试（双引号被转义成了字符，失去注入能力）
'''
如果没有转义代码（没有 replace），拼出来的字符串会变成：
tenant_id == "123" and course_id == "" or "1"="1"
'''
print("【例3】模拟注入攻击")
print('输入 tenant=tenant, course=" or "1"="1')
print("输出:", build_filter("tenant", '" or "1"="1'))