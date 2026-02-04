import importlib, traceback
importlib.invalidate_caches()
try:
    import main
    print('main imported OK')
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
