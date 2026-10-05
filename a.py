def dm01():
    yield 12
    print(123)

# for i in dm01():
#     print(i)
#     print("已进入")
dm_ge = dm01()
print(next(dm_ge))
print(next(dm_ge))