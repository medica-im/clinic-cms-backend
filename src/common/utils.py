import time

def timeit(func):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        elapsed = end - start
        print(f'{func.__name__} time taken: {elapsed:.6f} seconds')
        return result
    return wrapper

def timestamp()->int:
    """Return timestamp in milliseconds
    """
    return time.time_ns() // 1_000_000
