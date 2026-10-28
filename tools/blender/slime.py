"""Create the opaque clay slime; run with Blender 5.2:

blender -b --factory-startup -P tools/blender/slime.py

Design coordinates below are Godot metres: X right, Y up, +Z front.
Convert to Blender (x, -z, y) only when creating mesh data / transforms.
The exported Body origin stays at ground level for squash and stretch.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/slime/slime.glb"
COLORS = {"M_slime": "9C7BD6", "M_slime_light": "B9A0E6",
          "M_ink": "2B2233", "M_blush": "F2A0B8"}
SMOOTH_ANGLE = math.radians(40)
FACE_PIVOT = (0.0, 0.30, 0.33)


def reset_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material, do_unlink=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def linear_rgba(hex_rgb):
    def channel(c):
        c = int(c, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(channel(hex_rgb[i:i + 2]) for i in (0, 2, 4)) + (1.0,)


def make_material(name, hex_rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    color = linear_rgba(hex_rgb)
    mat.diffuse_color = color
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.85
    shader.inputs["Metallic"].default_value = 0.0
    shader.inputs["Specular IOR Level"].default_value = 0.3
    shader.inputs["Alpha"].default_value = 1.0
    shader.inputs["Transmission Weight"].default_value = 0.0
    return mat


def to_blender(p):
    return (p[0], -p[2], p[1])


def make_mesh(name, vertices, faces, materials, material_indices=None,
              parent=None, pivot=(0.0, 0.0, 0.0)):
    # Input vertices are in world/design Godot coordinates. Store them relative
    # to the requested pivot; never bake object location into the mesh.
    local = [to_blender(tuple(p[i] - pivot[i] for i in range(3))) for p in vertices]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(local, [], faces)
    mesh.update()
    for mat in materials:
        mesh.materials.append(mat)
    if material_indices is not None:
        for polygon, index in zip(mesh.polygons, material_indices):
            polygon.material_index = index
    # Same Smooth by Angle representation as rock.py, without applying location.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = not edge.is_manifold or edge.calc_face_angle() <= SMOOTH_ANGLE
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    obj.location = to_blender(pivot)  # Parents have the identity world transform.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.select_set(False)
    return obj


def body_geometry():
    """Broad flat foot, rolled lip, and a gently leaning, rounded droplet crown.

    Rings store (height, X radius, Z radius). The widest ring is centered at
    ground X/Z zero; only the crown leans. Explicit triangles also define the
    exact surface that the face and highlight shells will follow.
    """
    rings = ((0.000, 0.332, 0.307), (0.012, 0.359, 0.333),
             (0.034, 0.375, 0.350), (0.065, 0.371, 0.346),
             (0.110, 0.353, 0.330), (0.200, 0.330, 0.309),
             (0.300, 0.300, 0.280), (0.400, 0.257, 0.241),
             (0.480, 0.208, 0.195), (0.540, 0.151, 0.141),
             (0.578, 0.091, 0.085), (0.595, 0.043, 0.040))
    sectors = 32
    vertices = []
    for height, rx, rz in rings:
        lean = max(0.0, (height - 0.11) / 0.49) ** 2
        for i in range(sectors):
            angle = math.tau * i / sectors
            vertices.append((rx * math.cos(angle) + 0.028 * lean,
                             height, rz * math.sin(angle) - 0.018 * lean))
    faces = []
    for j in range(len(rings) - 1):
        for i in range(sectors):
            nxt = (i + 1) % sectors
            a, b = j * sectors + i, j * sectors + nxt
            c, d = a + sectors, b + sectors
            faces.extend(((a, c, d), (a, d, b)))
    top = len(vertices)
    vertices.append((0.028, 0.60, -0.018))
    last = (len(rings) - 1) * sectors
    bottom = len(vertices)
    vertices.append((0.0, 0.0, 0.0))
    for i in range(sectors):
        nxt = (i + 1) % sectors
        faces.append((last + i, top, last + nxt))
        faces.append((bottom, i, nxt))
    return vertices, faces


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def sub2(a, b):
    return (a[0] - b[0], a[1] - b[1])


def clip_polygon(polygon, triangle):
    """Intersect a convex decal with a CCW projected body triangle."""
    result = list(polygon)
    for i in range(3):
        a, b = triangle[i], triangle[(i + 1) % 3]
        edge = sub2(b, a)
        source, result = result, []
        if not source:
            break
        prev = source[-1]
        prev_dist = cross2(edge, sub2(prev, a))
        for current in source:
            dist = cross2(edge, sub2(current, a))
            if (dist >= 0) != (prev_dist >= 0):
                t = prev_dist / (prev_dist - dist)
                result.append(tuple(prev[k] + t * (current[k] - prev[k])
                                    for k in range(2)))
            if dist >= 0:
                result.append(current)
            prev, prev_dist = current, dist
    return result


def ellipse(cx, cy, rx, ry, segments=20):
    return [(cx + rx * math.cos(math.tau * i / segments),
             cy + ry * math.sin(math.tau * i / segments)) for i in range(segments)]


def capsule(a, b, radius, arc_steps=6):
    """A short eyebrow with soft rounded ends, CCW in the face plane."""
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    result = []
    for center, start in ((b, angle - math.pi / 2), (a, angle + math.pi / 2)):
        for i in range(arc_steps + 1):
            theta = start + math.pi * i / arc_steps
            result.append((center[0] + radius * math.cos(theta),
                           center[1] + radius * math.sin(theta)))
    return result


def surface_patch(body_vertices, body_faces, outline, axes, offset=0.0008):
    """Clip against real triangles, then lift 0.8 mm toward the viewer.

    This follows every body edge exactly: no ray-sampled chords sinking into
    the body, floating facial ellipsoids, textures, or transparency. The opaque
    open shell has no visible thickness at this scale. Axes are (u,v,depth).
    """
    u, v, depth = axes
    vertices, faces = [], []
    cache = {}
    low = [min(p[k] for p in outline) for k in range(2)]
    high = [max(p[k] for p in outline) for k in range(2)]
    for indices in body_faces:
        points = [body_vertices[i] for i in indices]
        normal = (Vector(points[1]) - Vector(points[0])).cross(
            Vector(points[2]) - Vector(points[0]))
        if normal[depth] <= 1e-12:
            continue
        tri = [(p[u], p[v]) for p in points]
        if any(max(p[k] for p in tri) < low[k] or
               min(p[k] for p in tri) > high[k] for k in range(2)):
            continue
        signed_area = cross2(sub2(tri[1], tri[0]), sub2(tri[2], tri[0]))
        if signed_area < 0:
            tri.reverse()
            points.reverse()
            signed_area = -signed_area
        clipped = clip_polygon(outline, tri)
        if len(clipped) < 3:
            continue
        polygon = []
        for p in clipped:
            w1 = cross2(sub2(p, tri[0]), sub2(tri[2], tri[0])) / signed_area
            w2 = cross2(sub2(tri[1], tri[0]), sub2(p, tri[0])) / signed_area
            coord = [0.0, 0.0, 0.0]
            coord[u], coord[v] = p
            coord[depth] = ((1 - w1 - w2) * points[0][depth]
                            + w1 * points[1][depth] + w2 * points[2][depth] + offset)
            key = tuple(round(c, 10) for c in coord)
            if key not in cache:
                cache[key] = len(vertices)
                vertices.append(tuple(coord))
            polygon.append(cache[key])
        for i in range(1, len(polygon) - 1):
            face = (polygon[0], polygon[i], polygon[i + 1])
            a, b, c = (Vector(vertices[j]) for j in face)
            n = (b - a).cross(c - a)
            if n.length_squared <= 1e-20:
                continue
            if n[depth] < 0:
                face = tuple(reversed(face))
            faces.append(face)
    assert faces, "Surface patch missed the body"
    return vertices, faces


def make_face(body, vertices, faces, materials):
    # Eye center spacing is 0.18 m; full oval size is 0.07 x 0.10 m.
    outlines = [(ellipse(x, 0.295, 0.035, 0.050), 0) for x in (-0.09, 0.09)]
    # Outer ends sit higher; inner ends descend for the angry-cute expression.
    outlines += [(capsule((-0.143, 0.388), (-0.057, 0.354), 0.008), 0),
                 (capsule((0.057, 0.354), (0.143, 0.388), 0.008), 0)]
    outlines += [(ellipse(x, 0.225, 0.035, 0.035), 1) for x in (-0.173, 0.173)]
    all_vertices, all_faces, slots = [], [], []
    for outline, slot in outlines:
        patch_vertices, patch_faces = surface_patch(vertices, faces, outline, (0, 1, 2))
        start = len(all_vertices)
        all_vertices.extend(patch_vertices)
        all_faces.extend(tuple(start + i for i in face) for face in patch_faces)
        slots.extend([slot] * len(patch_faces))
    return make_mesh("Face", all_vertices, all_faces,
                     [materials["M_ink"], materials["M_blush"]], slots,
                     parent=body, pivot=FACE_PIVOT)


def read_glb(path):
    """Verify the written GLB geometry, hierarchy, materials and world pivots."""
    data = path.read_bytes()
    assert struct.unpack_from("<4sII", data) == (b"glTF", 2, len(data))
    cursor, document, binary = 12, None, None
    while cursor < len(data):
        length, kind = struct.unpack_from("<II", data, cursor)
        payload = data[cursor + 8:cursor + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(payload)
        elif kind == 0x004E4942:
            binary = payload
        cursor += 8 + length
    assert document is not None and binary is not None, "Incomplete GLB"

    def accessor(index):
        a = document["accessors"][index]
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride)
                for i in range(a["count"])]

    positions, names, pivots, parents = [], [], {}, {}
    triangles = 0

    def walk(index, parent, parent_name=None):
        nonlocal triangles
        node = document["nodes"][index]
        name = node.get("name", "")
        assert name not in pivots, f"Duplicate node: {name}"
        names.append(name)
        parents[name] = parent_name
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4]
                            for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        world = parent @ local
        pivots[name] = world.translation.copy()
        if "mesh" in node:
            assert name != "Slime", "Slime must be an Empty"
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                points = accessor(primitive["attributes"]["POSITION"])
                positions.extend(world @ Vector(p) for p in points)
                index_count = (document["accessors"][primitive["indices"]]["count"]
                               if "indices" in primitive else len(points))
                assert index_count % 3 == 0
                triangles += index_count // 3
        for child in node.get("children", []):
            walk(child, world, name)

    roots = document["scenes"][document.get("scene", 0)]["nodes"]
    for index in roots:
        walk(index, Matrix.Identity(4))
    assert len(roots) == 1, "Expected one Slime root"
    assert set(names) == {"Slime", "Body", "Face", "BodyHighlight"}, names
    assert parents == {"Slime": None, "Body": "Slime", "Face": "Body",
                       "BodyHighlight": "Body"}, parents
    for name in ("Slime", "Body"):
        assert pivots[name].length < 1e-7, f"{name} pivot moved: {pivots[name]}"
    assert (pivots["Face"] - Vector(FACE_PIVOT)).length < 1e-6, pivots["Face"]
    assert triangles <= 3000, f"Hard triangle limit exceeded: {triangles}"
    assert triangles <= 1200, f"Triangle target exceeded: {triangles}"
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert all(abs(a - b) <= b * 0.10 for a, b in zip(size, (0.75, 0.60, 0.70))), size
    assert abs(lo[1]) < 1e-7, f"Ground contact moved: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6
    assert not document.get("cameras") and not document.get("textures")
    assert not document.get("animations") and not document.get("skins")
    assert "KHR_lights_punctual" not in document.get("extensions", {})
    materials = document["materials"]
    assert len(materials) <= 6
    assert sorted(m["name"] for m in materials) == sorted(COLORS)
    for material in materials:
        pbr = material["pbrMetallicRoughness"]
        assert abs(pbr.get("roughnessFactor", 1) - 0.85) < 1e-6
        assert pbr.get("metallicFactor", 1) == 0
        expected = linear_rgba(COLORS[material["name"]])
        assert all(abs(a - b) < 1e-6 for a, b in zip(pbr["baseColorFactor"], expected))
        assert material.get("alphaMode", "OPAQUE") == "OPAQUE"
        transmission = material.get("extensions", {}).get("KHR_materials_transmission", {})
        assert transmission.get("transmissionFactor", 0) == 0
    print(json.dumps({"glb_absolute_path": str(path.resolve()),
                      "file_size_bytes": len(data), "triangle_count": triangles,
                      "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
                      "godot_min_y_m": round(lo[1], 7), "object_names": names,
                      "material_names": [m["name"] for m in materials],
                      "body_pivot_godot": [round(v, 7) for v in pivots["Body"]]}))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    root = bpy.data.objects.new("Slime", None)
    bpy.context.scene.collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    vertices, faces = body_geometry()
    body = make_mesh("Body", vertices, faces, [materials["M_slime"]], parent=root)
    make_face(body, vertices, faces, materials)
    # A small upper/front-left crown patch, separate thin opaque geometry.
    highlight_vertices, highlight_faces = surface_patch(
        vertices, faces, ellipse(-0.115, 0.075, 0.100, 0.083, 24), (0, 2, 1))
    make_mesh("BodyHighlight", highlight_vertices, highlight_faces,
              [materials["M_slime_light"]], parent=body)
    bpy.context.view_layer.update()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj in (root, body) or obj.parent == body)
    bpy.context.view_layer.objects.active = body
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
