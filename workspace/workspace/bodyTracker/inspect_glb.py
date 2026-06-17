from pygltflib import GLTF2

path = r'C:\brunette.glb'
g = GLTF2().load(path)
print('nodes', len(g.nodes or []))
print('skins', len(g.skins or []))
for si, s in enumerate(g.skins or []):
    print('skin', si, 'skeleton', s.skeleton)
    print('joint count', len(s.joints))
    for j in s.joints[:67]:
        n = g.nodes[j]
        print(j, 'name=', n.name, 'children=', n.children, 'mesh=', n.mesh, 'skin=', n.skin)
