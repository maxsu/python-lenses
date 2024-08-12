import random
import pprint

i = None
indent = 0
TRACE = False
prev = None

def trace(func):
    if not TRACE:
        return func
    
    def wrapper(*args, **kwargs):
        global i, indent, prev
        indent_line = '| ' * indent
        prefix = f"i = {i}: "
        print(f"{indent_line}i = {i}: {func.__name__}({args},{f', {kwargs}' if kwargs else ''})")
        indent += 1
        result = func(*args, **kwargs)
        indent -= 1

        if prev == result:
            print(f"{indent_line} ...")
        else:
            _result = pprint.pformat(result).split('\n')
            line_1 = _result.pop(0)
            print(indent_line + prefix + line_1)
            for line in _result:
                print(f"{indent_line}{' '*(len(prefix))}{line}")

        prev = result
        return result
    return wrapper

@trace
def random_structure(n, m, initial=True):
    if n == 0:
        return random_value(n, m)
      
    if initial:
        global i
        i = 0
        return random_dict(n, m)

    return random.choice(generators)(n, m)

@trace
def random_dict(n, m):
    global i
    result = {}
    for k in range(random.randint(1, m)):
        i += 1
        snapshot = i
        substructure = random_structure(n-1, m, False)
        result[snapshot] = substructure
    return result

@trace
def random_list(n, m):
    global i
    result = []
    for k in range(random.randint(1, m)):
        i += 1
        substructure = random_structure(n-1, m, False)
        result.append(substructure)
    return result

@trace
def random_value(n, m):
    global i
    return f"value_{i}"

generators = [
    random_dict,
    random_list,
    random_value
]

print("Result:")
pprint.pprint(random_structure(7, 3))
