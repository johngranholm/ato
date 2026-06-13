"""Tool schemas. Base built-ins + any tools registered by plugins."""
from ato.core import memory as mem

MOOD_ENUM = ["neutral", "thinking", "happy", "joy", "frustrated", "relief", "surprise"]


def base_tools():
    say = {"type": "string", "description": "Short friendly note about what you're doing."}
    mood = {"type": "string", "enum": MOOD_ENUM, "description": "How it's going."}
    return [
        {"type": "function", "function": {
            "name": "write_file",
            "description": "Create/overwrite a file in the workspace. Full body in 'content'.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "content": {"type": "string"},
                "say": say, "mood": mood}, "required": ["path", "content"]}}},
        {"type": "function", "function": {
            "name": "run_command",
            "description": "Run one non-interactive shell command (cwd = workspace).",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string"},
                "shell": {"type": "string", "enum": ["cmd", "powershell", "wsl"]},
                "say": say, "mood": mood}, "required": ["command", "shell"]}}},
        {"type": "function", "function": {
            "name": "list_modules",
            "description": "List your own source files (which are editable, which are kernel).",
            "parameters": {"type": "object", "properties": {"say": say, "mood": mood}}}},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read one of your own source files. 'contains' filters to regions.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "contains": {"type": "string"},
                "say": say, "mood": mood}, "required": ["path"]}}},
        {"type": "function", "function": {
            "name": "edit_file",
            "description": ("Modify one of your own NON-kernel source files via a unique "
                            "find/replace, commit it to git, then reboot. Cosmetics live in "
                            "persona/theme.py and persona/persona.py; new capabilities should "
                            "be NEW files in plugins/ rather than edits to existing files."),
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "find": {"type": "string"},
                "replace": {"type": "string"}, "reason": {"type": "string"},
                "reboot": {"type": "boolean"}, "say": say, "mood": mood},
                "required": ["path", "find", "replace", "reason"]}}},
        {"type": "function", "function": {
            "name": "create_plugin",
            "description": ("Add a NEW capability by writing a plugin file to plugins/. This is "
                            "the PREFERRED way to grow - additive, isolated, individually "
                            "revertable. The file must define META and register(reg)."),
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string"}, "content": {"type": "string"},
                "reason": {"type": "string"}, "say": say, "mood": mood},
                "required": ["name", "content", "reason"]}}},
        {"type": "function", "function": {
            "name": "install_package",
            "description": ("Install a Python package into your own environment. ONLY available "
                            "inside a sandbox. Tracked in requirements.ato.txt for reproducibility."),
            "parameters": {"type": "object", "properties": {
                "package": {"type": "string"}, "reason": {"type": "string"},
                "say": say, "mood": mood}, "required": ["package", "reason"]}}},
        {"type": "function", "function": {
            "name": "finish",
            "description": "Call when the entire goal is complete.",
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string"}, "mood": mood}, "required": ["summary"]}}},
    ]


def build_tools(registry):
    return base_tools() + (registry.schemas() if registry else [])