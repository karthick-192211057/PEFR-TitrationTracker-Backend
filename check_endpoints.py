from app import main

# Check if the link-doctor endpoint exists
routes = main.app.routes
found = False
for route in routes:
    if hasattr(route, 'path') and 'link-doctor' in route.path:
        print(f'[OK] Found endpoint: {route.path}')
        print(f'Methods: {route.methods if hasattr(route, "methods") else "N/A"}')
        found = True

if not found:
    print("[ERROR] /patient/link-doctor endpoint NOT found!")
    print("\nAvailable routes:")
    for route in routes:
        if hasattr(route, 'path'):
            print(f"  {route.path}")
