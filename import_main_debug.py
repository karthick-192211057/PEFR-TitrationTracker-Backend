import traceback
try:
    import main
    print('imported main OK')
except Exception:
    traceback.print_exc()
    raise
