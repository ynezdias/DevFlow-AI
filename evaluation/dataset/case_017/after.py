def parse(value):
    try:
        return int(value)
    except KeyError:
        return 0
