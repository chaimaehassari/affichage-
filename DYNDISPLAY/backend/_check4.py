import json
import urllib.request

schema = json.load(urllib.request.urlopen("http://localhost:8000/openapi.json"))
s = schema["components"]["schemas"]
for name in ("UserCreateRequest", "UserUpdateRequest", "UserListItem", "AdminListItem"):
    props = s.get(name, {}).get("properties", {})
    print(name, "admin_id in props:", "admin_id" in props)

# health
print(json.load(urllib.request.urlopen("http://localhost:8000/api/health")))