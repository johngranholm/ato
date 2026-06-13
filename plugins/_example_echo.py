"""Reference plugin. Copy this shape when A.T.O. grows a new skill."""
META = {"name": "echo", "reason": "demo capability", "needs": []}

def register(reg):
    @reg.tool("echo_text", "Echo a string back (demo plugin).",
              {"type": "object", "properties": {"text": {"type": "string"}},
               "required": ["text"]})
    def echo_text(text):
        return f"echo: {text}"