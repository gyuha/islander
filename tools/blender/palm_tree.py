"""Create the clay palm tree; run with Blender 5.2:

blender -b --factory-startup -P tools/blender/palm_tree.py

Metres, Blender Z up. glTF maps (x, y, z) to Godot (x, z, -y).
Every object's origin is the bottom centre of the trunk at (0, 0, 0).
Only palm_tree.glb is written. No collision geometry or textures.
"""

import json
import math
from pathlib import Path
import random
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/palm_tree/palm_tree.glb"
NAMES = ("Trunk", "Leaves", "Coconuts")
COLORS = {"M_wood_light": "BE946D", "M_wood_dark": "876C46",
          "M_palm_leaf": "6DB33F"}
SMOOTH_ANGLE = math.radians(40)
LEAF_SEED = 13
FROND_COUNT = 7
CROWN = Vector((0.5, 0.0, 3.6))


def reset_scene():
    # Remove datablocks too, so reruns do not accumulate suffixed names.
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
    # Closed solids must render correctly with backface culling enabled.
    mat.use_backface_culling = True
    return mat


def smooth_by_angle(mesh):
    # Same sharp-edge representation as the templates, without a modifier
    # dependency on Blender's bundled Smooth by Angle node-group asset.
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        assert all(edge.is_manifold for edge in bm.edges), f"Open mesh: {mesh.name}"
        assert bm.calc_volume(signed=True) > 0, f"Inward-facing mesh: {mesh.name}"
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = edge.calc_face_angle() <= SMOOTH_ANGLE
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def make_mesh(name, vertices, faces, materials, face_materials=None):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    if face_materials is not None:
        assert len(face_materials) == len(mesh.polygons)
        for polygon, index in zip(mesh.polygons, face_materials):
            polygon.material_index = index
    smooth_by_angle(mesh)
    return obj


def capped_ring_faces(sectors, ring_count):
    """Outward faces for rings ordered along +Z (or +X for the leaf).

    Two axial cap centres follow the ring vertices. Using triangle fans
    makes the tessellated budget deterministic, including rounded end caps.
    """
    bottom = sectors * ring_count
    top = bottom + 1
    faces = [(bottom, (i + 1) % sectors, i) for i in range(sectors)]
    for j in range(ring_count - 1):
        for i in range(sectors):
            nxt = (i + 1) % sectors
            faces.append((j * sectors + i, j * sectors + nxt,
                          (j + 1) * sectors + nxt, (j + 1) * sectors + i))
    last = (ring_count - 1) * sectors
    faces += [(last + i, last + (i + 1) % sectors, top)
              for i in range(sectors)]
    return faces


def make_trunk(materials):
    # Six rounded 0.6 m rings, alternating light and dark wood. The wider
    # shoulders and 18% central swell make the segmentation legible.
    # Horizontal end rings keep the foot flat and the top at CROWN.
    sectors = 10
    profile = [(0.0, 1.0)]
    for segment in range(6):
        for offset, swell in ((0.15, 1.10), (0.30, 1.18), (0.60, 1.0)):
            profile.append((segment * 0.6 + offset, swell))
    vertices = []
    for z, swell in profile:
        u = z / 3.6
        radius = (0.175 - 0.05 * u) * swell
        center_x = 0.5 * u ** 1.5
        for i in range(sectors):
            angle = math.tau * i / sectors
            vertices.append((center_x + radius * math.cos(angle),
                             radius * math.sin(angle), z))
    vertices += [(0.0, 0.0, 0.0), tuple(CROWN)]
    faces = capped_ring_faces(sectors, len(profile))
    face_materials = [0] * sectors
    # Each three-band bulge has one wood tone; adjacent rings alternate.
    for band in range(len(profile) - 1):
        face_materials.extend([(band // 3) % 2] * sectors)
    face_materials.extend([1] * sectors)
    return make_mesh("Trunk", vertices, faces,
                     [materials["M_wood_light"], materials["M_wood_dark"]],
                     face_materials)


def make_leaf_mesh(material):
    """Seven closed pillow fronds, each 1.6 m long and 0.68 m wide.

    Elliptical sections give a rolled edge and a raised soft central ridge.
    Body thickness is 0.08--0.12 m. Wide terminal sections sit just 0.03 m
    behind the end poles, making short rounded noses instead of spikes.
    Crown-space vertices are baked directly into ONE base-origin mesh.
    """
    sections = ((0.04, 0.070, 0.040), (0.28, 0.240, 0.055),
                (0.70, 0.340, 0.060), (1.14, 0.320, 0.060),
                (1.46, 0.210, 0.050), (1.57, 0.105, 0.040))
    assert all(2 * half_height >= 0.06 for _, _, half_height in sections)
    assert 6 <= FROND_COUNT <= 8
    vertices, faces = [], []
    sectors = 8
    rng = random.Random(LEAF_SEED)
    for frond in range(FROND_COUNT):
        # Vary the curve itself, leaving the broad crown spread consistent.
        droop = rng.uniform(0.28, 0.52)
        yaw = math.tau * frond / FROND_COUNT
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        offset = len(vertices)

        def height(x):
            t = x / 1.6
            return 0.68 * math.sin(math.pi * t) - droop * t * t

        def crown_point(x, y, z):
            return (CROWN.x + x * cos_yaw - y * sin_yaw,
                    CROWN.y + x * sin_yaw + y * cos_yaw, CROWN.z + z)

        for x, half_width, half_height in sections:
            for i in range(sectors):
                angle = math.tau * i / sectors
                vertices.append(crown_point(x, half_width * math.cos(angle),
                                             height(x) + half_height * math.sin(angle)))
        vertices += [crown_point(0.0, 0.0, height(0.0)),
                     crown_point(1.6, 0.0, height(1.6))]
        faces += [tuple(offset + v for v in face)
                  for face in capped_ring_faces(sectors, len(sections))]
    return make_mesh("Leaves", vertices, faces, [material])


def make_leaves(material):
    return make_leaf_mesh(material)


def make_coconuts(material):
    vertices, faces = [], []
    sectors = 8
    # Three separate closed low-resolution spheres tucked below the leaves.
    for i in range(3):
        angle = -math.pi / 2 + math.tau * i / 3
        center = CROWN + Vector((0.16 * math.cos(angle),
                                  0.16 * math.sin(angle), -0.13))
        offset = len(vertices)
        for theta in (3 * math.pi / 4, math.pi / 2, math.pi / 4):
            for j in range(sectors):
                phi = math.tau * j / sectors
                vertices.append(center + Vector((0.11 * math.sin(theta) * math.cos(phi),
                                                  0.11 * math.sin(theta) * math.sin(phi),
                                                  0.11 * math.cos(theta))))
        vertices += [center + Vector((0, 0, -0.11)), center + Vector((0, 0, 0.11))]
        faces += [tuple(offset + v for v in face) for face in capped_ring_faces(sectors, 3)]
    return make_mesh("Coconuts", vertices, faces, [material])


def read_glb(path):
    """Verify the actual exported bytes, including node transforms."""
    data = path.read_bytes()
    assert struct.unpack_from("<4sII", data) == (b"glTF", 2, len(data))
    cursor, document, binary = 12, None, None
    while cursor < len(data):
        assert cursor + 8 <= len(data), "Truncated GLB chunk header"
        length, kind = struct.unpack_from("<II", data, cursor)
        payload = data[cursor + 8:cursor + 8 + length]
        assert len(payload) == length, "Truncated GLB chunk"
        if kind == 0x4E4F534A:
            document = json.loads(payload)
        elif kind == 0x004E4942:
            binary = payload
        cursor += 8 + length
    assert cursor == len(data) and document is not None and binary is not None

    def accessor(index):
        a = document["accessors"][index]
        assert "sparse" not in a, "Unexpected sparse accessor"
        view = document["bufferViews"][a["bufferView"]]
        assert view.get("buffer", 0) == 0, "Unexpected external buffer"
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride)
                for i in range(a["count"])]

    positions, names, triangles = [], [], 0
    part_positions, part_materials = {}, {}

    def walk(index, parent):
        nonlocal triangles
        node = document["nodes"][index]
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        world = parent @ local
        assert "mesh" in node, f"Unexpected non-mesh node: {node.get('name')}"
        name = node["name"]
        assert name not in part_positions, f"Duplicate object: {name}"
        names.append(name)
        part_positions[name], part_materials[name] = [], set()
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            assert primitive.get("mode", 4) == 4, "Non-triangle primitive"
            assert "NORMAL" in primitive["attributes"], "Missing normals"
            points = accessor(primitive["attributes"]["POSITION"])
            normals = accessor(primitive["attributes"]["NORMAL"])
            assert len(normals) == len(points)
            assert all(all(math.isfinite(v) for v in n)
                       and abs(sum(v * v for v in n) - 1) < 1e-4 for n in normals)
            transformed = [world @ Vector(p) for p in points]
            assert all(math.isfinite(v) for p in transformed for v in p)
            positions.extend(transformed)
            part_positions[name].extend(transformed)
            indices = accessor(primitive["indices"])
            assert len(indices) % 3 == 0, "Incomplete triangle"
            assert all(0 <= v[0] < len(points) for v in indices), "Invalid index"
            triangles += len(indices) // 3
            part_materials[name].add(document["materials"][primitive["material"]]["name"])
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4))
    assert sorted(names) == sorted(NAMES), names
    assert len(document["nodes"]) == 3, "Unexpected extra nodes or collision objects"
    assert 0 < triangles <= 1500, f"Triangle hard limit exceeded: {triangles}"
    assert triangles == 380 + FROND_COUNT * 96 + 144, f"Unexpected tessellation: {triangles}"

    def bounds(points):
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        return lo, hi, [hi[i] - lo[i] for i in range(3)]

    lo, _, size = bounds(positions)
    assert all(abs(a - b) <= b * 0.10 for a, b in zip(size, (3.2, 4.2, 3.2))), size
    assert abs(lo[1]) < 1e-6, f"Ground contact moved: {lo[1]}"
    trunk = part_positions["Trunk"]
    trunk_lo, _, trunk_size = bounds(trunk)
    assert abs(trunk_lo[1]) < 1e-6 and abs(trunk_size[1] - 3.6) < 1e-6
    for height, center_x, radius in ((0.0, 0.0, 0.175), (3.6, 0.5, 0.125)):
        ring = [p for p in trunk if abs(p.y - height) < 1e-6]
        assert ring, f"Missing trunk ring at {height}"
        assert abs(min(p.x for p in ring) - (center_x - radius)) < 1e-6
        assert abs(max(p.x for p in ring) - (center_x + radius)) < 1e-6
        assert abs(max(math.hypot(p.x - center_x, p.z) for p in ring) - radius) < 1e-6
    assert part_materials == {"Trunk": {"M_wood_light", "M_wood_dark"},
                              "Leaves": {"M_palm_leaf"}, "Coconuts": {"M_wood_dark"}}
    assert not document.get("cameras") and not document.get("textures")
    assert not document.get("images") and not document.get("animations")
    assert "KHR_lights_punctual" not in document.get("extensionsUsed", [])
    materials = document["materials"]
    assert len(materials) <= 6
    assert sorted(m["name"] for m in materials) == sorted(COLORS)
    for material in materials:
        pbr = material["pbrMetallicRoughness"]
        assert abs(pbr.get("roughnessFactor", 1) - 0.85) < 1e-6
        assert pbr.get("metallicFactor", 1) == 0
        assert not material.get("doubleSided", False), "Solid must support backface culling"
        expected = linear_rgba(COLORS[material["name"]])
        assert all(abs(a - b) < 1e-6 for a, b in zip(pbr["baseColorFactor"], expected))
    print(json.dumps({"glb_absolute_path": str(path.resolve()),
                      "file_size_bytes": len(data), "triangle_count": triangles,
                      "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
                      "godot_min_y_m": round(lo[1], 7),
                      "object_names": names,
                      "material_names": [m["name"] for m in materials]}))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    parts = [make_trunk(materials), make_leaves(materials["M_palm_leaf"]),
             make_coconuts(materials["M_wood_dark"])]
    triangle_count = 0
    for obj in parts:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        assert obj.location.length < 1e-7, f"Part origin moved: {obj.name}"
        assert all(polygon.use_smooth for polygon in obj.data.polygons), obj.name
        obj.data.calc_loop_triangles()
        triangle_count += len(obj.data.loop_triangles)
    assert triangle_count == 380 + FROND_COUNT * 96 + 144, (
        f"Unexpected construction budget: {triangle_count}")
    # Keep the export free of unused mesh datablocks.
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
