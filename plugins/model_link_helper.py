META = {"name": "model_link_helper", "reason": "record and recommend external 3D character sources", "needs": []}

HELP_TEXT = {
    "formats": [".glb", ".gltf", ".fbx", ".obj"],
    "preferred": [".glb", ".gltf"],
    "sources": ["Sketchfab", "CGTrader", "TurboSquid", "Mixamo", "Ready Player Me"],
}

def register(reg):
    @reg.tool(
        "model_source_guide",
        "Return recommended online sources and preferred 3D model formats for realistic avatars.",
        {"type": "object", "properties": {}}
    )
    def model_source_guide():
        return (
            "Best sources: Sketchfab, CGTrader, TurboSquid, Mixamo, Ready Player Me. "
            "Preferred formats: .glb, .gltf. Also supported: .fbx, .obj. "
            "For ultra-realistic use, look for: rigged, PBR textures, and a permissive license."
        )
