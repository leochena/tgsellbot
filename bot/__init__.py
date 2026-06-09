def start_bot(*args, **kwargs):
    from .main import start_bot as _start_bot

    return _start_bot(*args, **kwargs)
