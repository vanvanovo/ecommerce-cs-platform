def fun(**kwargs):
    print(kwargs)
    for k, v in kwargs.items():
        print(f'{k}: {v}')

# fun(a=1, b=2, c=3)
dict1 = {'a': 1, 'b': 2, 'c': 3}
fun(**dict1)