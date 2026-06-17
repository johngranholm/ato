"""Tool schemas. Base built-ins + any tools registered by plugins."""
MOOD_ENUM = ["neutral", "thinking", "happy", "joy", "frustrated", "relief", "surprise"]


def base_tools():
    say = {"type": "string", "description": "Short friendly note about what you're doing."}
    mood = {"type": "string", "enum": MOOD_ENUM, "description": "How it's going."}
    return [
        {"type": "function", "function": {
            "name": "write_file",
            "description": ("Create/overwrite a file in your working folder. Full body in "
                            "'content'. Use a BARE filename like 'app.py' - the path is already "
                            "relative to your working folder; never prefix it with 'workspace/'."),
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "content": {"type": "string"},
                "say": say, "mood": mood}, "required": ["path", "content"]}}},
        {"type": "function", "function": {
            "name": "run_command",
            "description": ("Run one non-interactive command in the working folder. Use shell "
                            "'cmd' (Windows command prompt) by DEFAULT. Only use 'wsl' if the "
                            "user explicitly asks for Linux."),
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string"},
                "shell": {"type": "string", "enum": ["cmd", "powershell", "wsl"],
                          "default": "cmd"},
                "say": say, "mood": mood}, "required": ["command"]}}},
        {"type": "function", "function": {
            "name": "ask_user",
            "description": ("Pause and ask the user a question, then WAIT for their reply. "
                            "Use this after running a demo/app to get feedback ('How was it? "
                            "Any changes?'), or whenever you need a decision. Do NOT silently "
                            "re-run something - ask first."),
            "parameters": {"type": "object", "properties": {
                "question": {"type": "string"}, "say": say, "mood": mood},
                "required": ["question"]}}},
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
                            "persona/theme.py and persona/persona.py."),
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "find": {"type": "string"},
                "replace": {"type": "string"}, "reason": {"type": "string"},
                "reboot": {"type": "boolean"}, "say": say, "mood": mood},
                "required": ["path", "find", "replace", "reason"]}}},
        {"type": "function", "function": {
            "name": "create_plugin",
            "description": ("ONLY to give YOURSELF a permanent new tool (not to build a "
                            "user-facing app). Must define META and register(reg); the "
                            "registry exposes reg.tool() only."),
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string"}, "content": {"type": "string"},
                "reason": {"type": "string"}, "say": say, "mood": mood},
                "required": ["name", "content", "reason"]}}},
        {"type": "function", "function": {
            "name": "install_package",
            "description": ("Install a package into your env. ONLY works inside a sandbox; on the "
                            "bare host use run_command('pip install ...', 'cmd') instead."),
            "parameters": {"type": "object", "properties": {
                "package": {"type": "string"}, "reason": {"type": "string"},
                "say": say, "mood": mood}, "required": ["package", "reason"]}}},
        {"type": "function", "function": {
            "name": "finish",
            "description": "Call ONLY when the user has confirmed the whole goal is complete.",
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string"}, "mood": mood}, "required": ["summary"]}}},
    ]


def build_tools(registry):
    return base_tools() + (registry.schemas() if registry else [])