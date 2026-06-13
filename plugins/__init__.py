"""
Plugin loader: A.T.O. grows by ADDING files here. Each plugin defines:
    META = {"name": ..., "reason": ..., "needs": [pip names]}
    def register(reg): reg.tool(name, desc)(fn)
"""
import os
import glob
import importlib.util

from ato import config


class ToolRegistry:
    def __init__(self):
        self.fns = {}        # name -> callable
        self._schemas = []   # openai tool schemas

    def tool(self, name, description, params=None):
        def deco(fn):
            self.fns[name] = fn
            self._schemas.append({"type": "function", "function": {
                "name": name, "description": description,
                "parameters": params or {"type": "object", "properties": {}}}})
            return fn
        return deco

    # alias so plugins that guess this name still work (self-healing)
    def register_command(self, name, description, params=None):
        return self.tool(name, description, params)

    # second common guess -> same thing
    def register_tool(self, name, description, params=None):
        return self.tool(name, description, params)

    def schemas(self):
        return list(self._schemas)


def load_plugins(emit=None):
    reg = ToolRegistry()
    loaded = []
    for path in sorted(glob.glob(os.path.join(config.PLUGIN_DIR, "*.py"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            src = open(path, "r", encoding="utf-8").read()
            compile(src, path, "exec")                 # preflight
            spec = importlib.util.spec_from_file_location(
                "ato_plugin_" + os.path.splitext(os.path.basename(path))[0], path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register"):
                module.register(reg)
                loaded.append(getattr(module, "META", {}).get("name", os.path.basename(path)))
        except Exception as e:
            if emit:
                emit("error", f"plugin {os.path.basename(path)} failed to load: {e}",
                     mood="frustrated")
    if emit and loaded:
        emit("system", "Loaded plugins: " + ", ".join(loaded))
    return reg