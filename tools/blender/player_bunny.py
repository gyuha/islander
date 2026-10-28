"""Build the unrigged clay bunny; run externally with Blender 5.2:

    blender -b --factory-startup -P tools/blender/player_bunny.py

Construction coordinates are Godot metres: +Y up, +Z facing forward.
Only rotation and scale are applied. Joint origins survive as translations.
No backpack, axe, collision, textures, lights, cameras, or animation is exported.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/player_bunny/player_bunny.glb"
COLORS = {
    "M_white_warm": "F9F6E5",
    "M_ink": "2B2233",
    "M_blush": "F2A0B8",
    "M_orange": "E79C62",
}
SMOOTH_ANGLE = math.radians(40)
PIVOTS = {
    "PlayerBunny": (0, 0, 0),
    "Body": (0, 0.18, 0),
    "Head": (0, 0.44, 0),
    "EarL": (0.09, 0.78, -0.02),
    "EarR": (-0.09, 0.78, -0.02),
    "ArmL": (0.20, 0.38, 0),
    "ArmR": (-0.20, 0.38, 0),
    "ToolSocket": (-0.21, 0.22, 0.04),
    "LegL": (0.09, 0.18, 0),
    "LegR": (-0.09, 0.18, 0),
}
PARENTS = {
    "PlayerBunny": None,
    "Body": "PlayerBunny",
    "Head": "Body",
    "EarL": "Head",
    "EarR": "Head",
    "ArmL": "Body",
    "ArmR": "Body",
    "ToolSocket": "ArmR",
    "LegL": "PlayerBunny",
    "LegR": "PlayerBunny",
}
MESH_NAMES = set(PIVOTS) - {"PlayerBunny", "ToolSocket"}


def reset_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


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
    return mat


def to_blender(p):
    return (p[0], -p[2], p[1])


class Part:
    """Accumulate disconnected coloured solids into ONE named part mesh."""

    def __init__(self):
        self.vertices = []
        self.faces = []
        self.material_indices = []

    def add(self, vertices, faces, material):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset + i for i in face) for face in faces)
        self.material_indices.extend([list(COLORS).index(material)] * len(faces))

    def rings(self, profiles, segments, transform, material):
        """Closed rounded solid; profiles are (height, x radius, z radius).

        Zero-radius endpoints become single poles, avoiding degenerate faces.
        A nonzero endpoint is closed by a flat polygon (used for soles).
        """
        vertices, rings, faces = [], [], []
        for height, rx, rz in profiles:
            if rx == 0 and rz == 0:
                rings.append([len(vertices)])
                vertices.append(transform((0, height, 0)))
            else:
                ring = []
                for i in range(segments):
                    angle = math.tau * i / segments
                    ring.append(len(vertices))
                    vertices.append(transform((rx * math.cos(angle), height,
                                               rz * math.sin(angle))))
                rings.append(ring)
        if len(rings[0]) > 1:
            faces.append(tuple(rings[0]))
        for lower, upper in zip(rings, rings[1:]):
            for i in range(segments):
                j = (i + 1) % segments
                if len(lower) == 1:
                    faces.append((lower[0], upper[i], upper[j]))
                elif len(upper) == 1:
                    faces.append((lower[i], upper[0], lower[j]))
                else:
                    faces.append((lower[i], upper[i], upper[j], lower[j]))
        if len(rings[-1]) > 1:
            faces.append(tuple(reversed(rings[-1])))
        self.add(vertices, faces, material)

    def ellipsoid(self, center, size, material, segments=12, steps=6, warp=None):
        profiles = [(-1, 0, 0)]
        for j in range(1, steps):
            a = math.pi * j / steps
            profiles.append((-math.cos(a), math.sin(a), math.sin(a)))
        profiles.append((1, 0, 0))

        def transform(p):
            if warp is not None:
                p = warp(p)
            return tuple(center[i] + p[i] * size[i] / 2 for i in range(3))

        self.rings(profiles, segments, transform, material)

    def capsule(self, center_xz, bottom, height, width, depth, material,
                segments=12, transform=None):
        cap = width / 2
        k = math.sqrt(0.5)
        profiles = [(0, 0, 0),
                    (cap * (1 - k), width * k / 2, depth * k / 2),
                    (cap, width / 2, depth / 2),
                    (height - cap, width / 2, depth / 2),
                    (height - cap * (1 - k), width * k / 2, depth * k / 2),
                    (height, 0, 0)]

        def place(p):
            q = (p[0] + center_xz[0], p[1] + bottom, p[2] + center_xz[1])
            return transform(q) if transform is not None else q

        self.rings(profiles, segments, place, material)

    def finish(self, name, materials, parent):
        pivot = PIVOTS[name]
        vertices = [to_blender(tuple(p[i] - pivot[i] for i in range(3)))
                    for p in self.vertices]
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata(vertices, [], self.faces)
        mesh.update()
        for material in materials.values():
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, self.material_indices):
            polygon.material_index = index
        # Blender 5.2 Smooth by Angle: smooth polygons and sharp edges >40 deg.
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = not edge.is_manifold or edge.calc_face_angle() <= SMOOTH_ANGLE
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        attach(obj, name, parent)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        # NEVER apply location: joint origins must remain glTF node translations.
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.select_set(False)
        return obj


def attach(obj, name, parent):
    obj.parent = parent
    parent_pivot = PIVOTS[PARENTS[name]] if parent is not None else (0, 0, 0)
    obj.location = to_blender(tuple(PIVOTS[name][i] - parent_pivot[i] for i in range(3)))
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)


def make_empty(name, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.04
    attach(obj, name, parent)
    return obj


def make_body():
    part = Part()
    # Normalize the sampled egg's widest ring to the specified 0.38 x 0.32.
    widest = max(math.sin(math.pi * j / 8) * (1 + 0.18 * math.cos(math.pi * j / 8))
                 for j in range(1, 8))

    def egg(p):
        factor = (1 - 0.18 * p[1]) / widest
        return (p[0] * factor, p[1], p[2] * factor)

    part.ellipsoid((0, 0.30, 0), (0.38, 0.32, 0.32), "M_white_warm", 16, 8, egg)
    part.ellipsoid((0, 0.22, -0.18), (0.10, 0.10, 0.10), "M_white_warm", 12, 6)
    # Flattened torus, elliptical in plan, around the actual neck intersection.
    vertices, faces = [], []
    major, minor = 16, 6
    for i in range(major):
        a = math.tau * i / major
        for j in range(minor):
            b = math.tau * j / minor
            vertices.append(((0.119 + 0.022 * math.cos(b)) * math.cos(a),
                             0.432 + 0.015 * math.sin(b),
                             (0.102 + 0.022 * math.cos(b)) * math.sin(a)))
    for i in range(major):
        for j in range(minor):
            faces.append((i * minor + j, ((i + 1) % major) * minor + j,
                          ((i + 1) % major) * minor + (j + 1) % minor,
                          i * minor + (j + 1) % minor))
    part.add(vertices, faces, "M_orange")
    part.ellipsoid((0.035, 0.424, 0.121), (0.063, 0.042, 0.043), "M_orange", 10, 4)
    for x, bottom, height in ((0.022, 0.347, 0.075), (0.052, 0.365, 0.060)):
        part.capsule((x, 0.147), bottom, height, 0.028, 0.012, "M_orange", 8)
    return part


def head_front(x, y):
    return 0.20 * math.sqrt(max(0, 1 - (x / 0.23) ** 2 - ((y - 0.62) / 0.20) ** 2))


def face_oval(part, x, y, width, height, depth, material, segments=10, steps=5,
              lift=0.001):
    # Curve each coloured patch onto the head; the back intersects the fur and
    # the shallow front remains visible along the whole ellipse, with no gaps.
    def conform(p):
        px, py = x + p[0] * width / 2, y + p[1] * height / 2
        return (px, py, head_front(px, py) + lift + p[2] * depth / 2)

    profiles = [(-1, 0, 0)]
    for j in range(1, steps):
        a = math.pi * j / steps
        profiles.append((-math.cos(a), math.sin(a), math.sin(a)))
    profiles.append((1, 0, 0))
    part.rings(profiles, segments, conform, material)


def make_nose(part):
    # Bevel a small inverted triangle in the face plane, then round its front.
    corners = [(-0.015, 0.010), (0, -0.014), (0.015, 0.010)]
    outline = []
    for i, corner in enumerate(corners):
        previous, following = corners[(i - 1) % 3], corners[(i + 1) % 3]
        a = tuple(0.75 * corner[k] + 0.25 * previous[k] for k in range(2))
        b = tuple(0.75 * corner[k] + 0.25 * following[k] for k in range(2))
        for j in range(4):
            t = j / 3
            outline.append(tuple((1 - t) ** 2 * a[k] + 2 * (1 - t) * t * corner[k]
                                 + t * t * b[k] for k in range(2)))
    scale_x = 0.03 / (max(p[0] for p in outline) - min(p[0] for p in outline))
    vertices = []
    for scale, depth in ((1, -0.001), (0.82, 0.005)):
        for x, y in outline:
            px, py = x * scale_x * scale, 0.598 + y * scale
            vertices.append((px, py, head_front(px, py) + depth))
    count = len(outline)
    vertices.append((0, 0.598, head_front(0, 0.598) + 0.007))
    faces = [tuple(reversed(range(count)))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, count + j, count + i))
        faces.append((count + i, count + j, 2 * count))
    part.add(vertices, faces, "M_blush")


def mouth_stroke(part, points, radius=0.0018):
    vertices, faces = [], []
    sides = 5
    for i, (x, y) in enumerate(points):
        previous, following = points[max(0, i - 1)], points[min(len(points) - 1, i + 1)]
        dx, dy = following[0] - previous[0], following[1] - previous[1]
        length = math.hypot(dx, dy)
        for j in range(sides):
            a = math.tau * j / sides
            px, py = x + dy / length * radius * math.cos(a), y - dx / length * radius * math.cos(a)
            vertices.append((px, py, head_front(px, py) + 0.002 + radius * math.sin(a)))
    faces.append(tuple(reversed(range(sides))))
    for i in range(len(points) - 1):
        for j in range(sides):
            k = (j + 1) % sides
            faces.append((i * sides + j, i * sides + k,
                          (i + 1) * sides + k, (i + 1) * sides + j))
    faces.append(tuple((len(points) - 1) * sides + j for j in range(sides)))
    part.add(vertices, faces, "M_ink")


def make_head():
    part = Part()
    part.ellipsoid((0, 0.62, 0), (0.46, 0.40, 0.40), "M_white_warm", 20, 10)
    for sign in (-1, 1):
        face_oval(part, sign * 0.07, 0.62, 0.05, 0.07, 0.010, "M_ink", 12, 6)
        face_oval(part, sign * 0.132, 0.578, 0.06, 0.06, 0.003, "M_blush", 12, 4)
        face_oval(part, sign * 0.07 - 0.006, 0.635, 0.010, 0.014, 0.003,
                  "M_white_warm", 6, 4, lift=0.007)
        mouth_stroke(part, [(0, 0.583), (sign * 0.008, 0.576),
                            (sign * 0.018, 0.578), (sign * 0.026, 0.586)])
    make_nose(part)
    mouth_stroke(part, [(0, 0.589), (0, 0.583)])
    return part


def make_ear(sign):
    part = Part()
    angle = math.radians(10)
    # 4.9 mm overlap above the joint seats the 0.32 m capsule into the head,
    # while its tilted tip lands at exactly 1.10 m. The joint stays at y=0.78.
    base_y = 1.10 - 0.32 * math.cos(angle)

    def place(p):
        x, y, z = p
        return (sign * 0.09 + x * math.cos(angle) + sign * y * math.sin(angle),
                base_y + y * math.cos(angle) - sign * x * math.sin(angle),
                -0.02 + z)

    part.capsule((0, 0), 0, 0.32, 0.11, 0.06, "M_white_warm", 12, place)

    def inner_plate(p):
        x, y, z = p
        cap_y = min(y, 0.32 - y, 0.055)
        cap_scale = math.sqrt(max(0, 1 - ((0.055 - cap_y) / 0.055) ** 2))
        white_front = 0.03 * math.sqrt(max(0, cap_scale ** 2 - (x / 0.055) ** 2))
        return place((x, y, white_front + 0.001 + z))

    # A closed, 3 mm thick applied plate, never a hollow or recessed ear.
    part.capsule((0, 0), 0.040, 0.245, 0.062, 0.003, "M_blush", 10, inner_plate)
    return part


def make_arm(sign):
    part = Part()
    part.capsule((sign * 0.20, 0.01), 0.21, 0.17, 0.09, 0.09, "M_white_warm", 12)
    return part


def make_leg(sign):
    part = Part()
    profiles = [(0, 0.043, 0.043), (0.006, 0.052, 0.052),
                (0.025, 0.06, 0.06), (0.12, 0.06, 0.06),
                (0.1624264069, 0.0424264069, 0.0424264069), (0.18, 0, 0)]

    def place(p):
        x, y, z = p
        return (sign * 0.09 + x, y, z + 0.03 * (1 - y / 0.18))

    # Build as one solid, then colour the flat sole and its rounded lower lip.
    part.rings(profiles, 12, place, "M_white_warm")
    blush = list(COLORS).index("M_blush")
    part.material_indices[0:13] = [blush] * 13
    return part


def read_glb(path):
    """Independently check actual GLB vertices and WORLD node transforms."""
    data = path.read_bytes()
    assert struct.unpack_from("<4sII", data) == (b"glTF", 2, len(data)), "Invalid GLB header"
    cursor, document, binary = 12, None, None
    while cursor < len(data):
        length, kind = struct.unpack_from("<II", data, cursor)
        payload = data[cursor + 8:cursor + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(payload)
        elif kind == 0x004E4942:
            binary = payload
        cursor += 8 + length
    assert document is not None and binary is not None, "Missing GLB chunks"

    def accessor(index):
        a = document["accessors"][index]
        assert "sparse" not in a, "Unexpected sparse accessor"
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride) for i in range(a["count"])]

    positions, part_positions, pivots, parents, mesh_names = [], {}, {}, {}, []
    triangles = 0

    def walk(index, parent_matrix, parent_name):
        nonlocal triangles
        node = document["nodes"][index]
        name = node["name"]
        assert name not in pivots, f"Duplicate node: {name}"
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        assert all(abs(local[r][c] - float(r == c)) < 1e-6
                   for r in range(3) for c in range(3)), f"Unapplied rotation/scale: {name}"
        world = parent_matrix @ local
        pivots[name] = list(world.translation)
        parents[name] = parent_name
        if "mesh" in node:
            mesh_names.append(name)
            points_for_part = []
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], f"Missing smooth normals: {name}"
                points = [world @ Vector(p) for p in accessor(primitive["attributes"]["POSITION"])]
                points_for_part.extend(points)
                indices = accessor(primitive["indices"]) if "indices" in primitive else points
                assert len(indices) % 3 == 0, "Incomplete triangle"
                triangles += len(indices) // 3
            positions.extend(points_for_part)
            part_positions[name] = points_for_part
        for child in node.get("children", []):
            walk(child, world, name)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4), None)
    assert set(pivots) == set(PIVOTS), f"Unexpected nodes: {list(pivots)}"
    assert len(document["nodes"]) == len(PIVOTS), "Extra unreachable nodes"
    assert set(mesh_names) == MESH_NAMES, f"Unexpected mesh nodes: {mesh_names}"
    assert len(document["meshes"]) == len(MESH_NAMES), "Unexpected mesh count"
    assert parents == PARENTS, f"Incorrect hierarchy: {parents}"
    for name, expected in PIVOTS.items():
        assert all(abs(actual - target) <= 0.01 for actual, target in zip(pivots[name], expected)), (
            f"World pivot mismatch: {name}: {pivots[name]} != {expected}")
        parent_pivot = PIVOTS[PARENTS[name]] if PARENTS[name] else (0, 0, 0)
        node = next(n for n in document["nodes"] if n["name"] == name)
        expected_local = [expected[i] - parent_pivot[i] for i in range(3)]
        assert all(abs(a - b) < 1e-6 for a, b in zip(node.get("translation", [0, 0, 0]), expected_local)), (
            f"Local joint translation lost: {name}")
    low = [min(p[i] for p in positions) for i in range(3)]
    high = [max(p[i] for p in positions) for i in range(3)]
    size = [high[i] - low[i] for i in range(3)]
    assert triangles <= 3000, f"Hard triangle limit exceeded: {triangles}"
    assert triangles <= 2500, f"Triangle target exceeded: {triangles}"
    assert 0.46 * 0.9 <= size[0] <= 0.46 * 1.1, f"Width outside tolerance: {size[0]}"
    assert abs(size[1] - 1.10) < 1e-5, f"Ear-tip height: {size[1]}"
    assert abs(low[1]) < 1e-7, f"Ground contact moved: {low[1]}"
    without_ears = [p for name, points in part_positions.items() if not name.startswith("Ear") for p in points]
    assert abs(max(p.y for p in without_ears) - 0.82) < 1e-6, "Incorrect height excluding ears"
    assert abs(low[0] + high[0]) < 1e-6, "Silhouette is not centred between feet"
    for name in ("LegL", "LegR"):
        assert abs(min(p.y for p in part_positions[name])) < 1e-7, f"Floating foot: {name}"
        assert abs(max(p.y for p in part_positions[name]) - 0.18) < 1e-6
    head_points = part_positions["Head"]
    assert abs(max(p.x for p in head_points) - min(p.x for p in head_points) - 0.46) < 1e-6
    assert not document.get("cameras") and not document.get("textures") and not document.get("images")
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
        assert not any("Texture" in key for key in pbr), "Unexpected texture"
    # Verify face direction using exported ink/blush primitives, rather than a
    # construction-time flag: every facial patch must lie on the +Z hemisphere.
    nodes_by_name = {node["name"]: node for node in document["nodes"]}
    head_mesh = document["meshes"][nodes_by_name["Head"]["mesh"]]
    for primitive in head_mesh["primitives"]:
        material_name = materials[primitive["material"]]["name"]
        if material_name in {"M_ink", "M_blush"}:
            points = accessor(primitive["attributes"]["POSITION"])
            assert min(p[2] + pivots["Head"][2] for p in points) > 0.12, "Face must point +Z"
    print(json.dumps({
        "glb_absolute_path": str(path.resolve()),
        "file_size_bytes": len(data),
        "triangle_count": triangles,
        "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
        "godot_min_y_m": round(low[1], 7),
        "object_names": list(pivots),
        "material_names": [m["name"] for m in materials],
        "pivots": {name: [round(v, 7) for v in p] for name, p in pivots.items()},
    }, indent=2))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    objects = {"PlayerBunny": make_empty("PlayerBunny")}
    builders = {
        "Body": make_body,
        "Head": make_head,
        "EarL": lambda: make_ear(1),
        "EarR": lambda: make_ear(-1),
        "ArmL": lambda: make_arm(1),
        "ArmR": lambda: make_arm(-1),
        "LegL": lambda: make_leg(1),
        "LegR": lambda: make_leg(-1),
    }
    for name in PIVOTS:
        if name == "PlayerBunny":
            continue
        parent = objects[PARENTS[name]]
        objects[name] = (make_empty(name, parent) if name == "ToolSocket"
                         else builders[name]().finish(name, materials, parent))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj.name in PIVOTS)
    bpy.context.view_layer.objects.active = objects["PlayerBunny"]
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
