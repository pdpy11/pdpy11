import os


resources = {}
resources_path = os.path.join(os.path.dirname(__file__), "resources")
for name in os.listdir(resources_path):
    with open(os.path.join(resources_path, name), "rb") as f:
        resources[name] = f.read()
