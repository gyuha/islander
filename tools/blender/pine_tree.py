"""Create the clay pine tree. Run: blender -b --factory-startup -P tools/blender/pine_tree.py.

All construction is in metres, Blender Z up. The exporter maps (x, y, z)
to Godot/glTF (x, z, -y). The trunk's bottom centre is the origin.
Only this repository's pine_tree.glb is written; no blend file is needed.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/pine_tree/pine_tree.glb"
NAMES = ("Trunk", "Tier1", "Tier2", "Tier3")
COLORS = {"M_trunk": "8A5A3B", "M_leaf_dark": "2F8F57",
          "M_leaf": "3FA463", "M_leaf_shadow": "285538"}
SMOOTH_ANGLE = math.radians(40)
PART_SPECS = {
    "Trunk": ((0.45, 1.0, 0.45), 0.0, "M_trunk"),
    "Tier1": ((2.2, 1.3, 2.2), 0.7, "M_leaf_dark"),
    "Tier2": ((1.7, 1.1, 1.7), 1.6, "M_leaf"),
    "Tier3": ((1.1, 1.0, 1.1), 2.6, "M_leaf"),
}


def reset_scene():
    # Removing datablocks, rather than just unlinking objects, makes reruns clean.
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


def make_mesh(name, vertices, faces, materials, face_materials):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    assert len(face_materials) == len(mesh.polygons)
    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index
    # Blender 5.2 Smooth by Angle's underlying sharp-edge representation.
    # Smooth polygons retain normal discontinuities only at angles over 40 deg.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    assert all(edge.is_manifold for edge in bm.edges), f"Open mesh: {name}"
    assert bm.calc_volume(signed=True) > 0, f"Inward-facing mesh: {name}"
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = edge.calc_face_angle() <= SMOOTH_ANGLE
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.select_set(False)
    return obj


def lathe(name, sectors, profile, bottom, top, materials,
          ring_sectors=None, scallop_weights=None):
    """Closed, outward-wound rings with flat bottom and a top cap or pole.

    profile contains absolute (height, radius) pairs. Separate cap centres
    avoid large n-gons and make the exported triangle budget deterministic.
    The optional second material shades the underside and lower rolled lip.
    Rings may halve their sector count towards the cap; each transition uses
    three triangles per pair of lower edges. Eight cosine lobes roll the
    skirt inward and upward between the rounded, low-hanging lobe tips.
    """
    counts = ring_sectors if ring_sectors is not None else [sectors] * len(profile)
    weights = scallop_weights if scallop_weights is not None else [0.0] * len(profile)
    assert len(counts) == len(weights) == len(profile)
    vertices, starts = [], []
    for (height, radius), count, weight in zip(profile, counts, weights):
        starts.append(len(vertices))
        for i in range(count):
            angle = math.tau * i / count
            valley = 0.5 * (1.0 - math.cos(8 * angle))
            r = radius * (1.0 - 0.09 * weight * valley)
            z = height + 0.035 * (top - bottom) * weight * valley
            vertices.append((r * math.cos(angle), r * math.sin(angle), z))
    bottom_index = len(vertices)
    vertices.append((0.0, 0.0, bottom))
    top_index = len(vertices)
    vertices.append((0.0, 0.0, top))
    faces, face_materials = [], []
    underside = 1 if len(materials) > 1 else 0
    for i in range(counts[0]):
        nxt = (i + 1) % counts[0]
        faces.append((bottom_index, nxt, i))
        face_materials.append(underside)
    for j in range(len(profile) - 1):
        lower, upper = starts[j], starts[j + 1]
        count, next_count = counts[j], counts[j + 1]
        if count == next_count:
            for i in range(count):
                nxt = (i + 1) % count
                faces.append((lower + i, lower + nxt, upper + nxt, upper + i))
                face_materials.append(underside if j == 0 else 0)
        else:
            assert count == 2 * next_count, "Rings must keep or halve their sectors"
            for i in range(next_count):
                a, b, c = (lower + (2 * i + k) % count for k in range(3))
                d, e = upper + i, upper + (i + 1) % next_count
                faces.extend(((a, b, d), (b, e, d), (b, c, e)))
                face_materials.extend([underside if j == 0 else 0] * 3)
    last, count = starts[-1], counts[-1]
    for i in range(count):
        faces.append((last + i, last + (i + 1) % count, top_index))
        face_materials.append(0)
    return make_mesh(name, vertices, faces, materials, face_materials)


def make_trunk(material):
    # Short tapered cylinder; the bottom is exactly flat at ground level.
    return lathe("Trunk", 12,
                 ((0.0, 0.225), (0.045, 0.222),
                  (0.955, 0.178), (1.0, 0.175)),
                 0.0, 1.0, [material])


def make_tier(name, diameter, height, bottom, material, shadow):
    # Four close, 32-sector lower rings round over eight scalloped lobes.
    # Cosine peaks lie on both horizontal axes, preserving the exact bbox.
    # The waves fade above the skirt; their maximum radius is diameter / 2.
    # The main cone is inflated 6.5% at mid-height relative to the straight
    # cone from the shoulder (u=0.11) to the summit (u=1). Three upper rings
    # turn into a small dome with a shallow, nearly horizontal top fan.
    # Reducing sectors only above the skirt keeps the total at 1,248 tris:
    # 384 per tier (caps 32+8, bands 192+48+64+24+16), plus the 96-tri trunk.
    def inflated_radius(u):
        return ((1.0 - u) / 0.89
                * (1.0 + 0.065 * math.sin(math.pi * (u - 0.11) / 0.89)))

    profile = ((0.0, 0.88), (0.025, 0.955), (0.065, 0.99),
               (0.11, 1.0), (0.20, 0.97),
               (0.50, inflated_radius(0.50)),
               (0.90, inflated_radius(0.90)),
               (0.977, 0.075), (0.995, 0.035))
    assert 0.05 <= inflated_radius(0.5) / (0.5 / 0.89) - 1.0 <= 0.08
    rings = [(bottom + u * height, radius * diameter / 2)
             for u, radius in profile]
    return lathe(name, 32, rings, bottom, bottom + height, [material, shadow],
                 ring_sectors=(32, 32, 32, 32, 16, 16, 16, 8, 8),
                 scallop_weights=(1.0, 1.0, 0.85, 0.60, 0.10, 0.0, 0.0, 0.0, 0.0))


def read_glb(path):
    """Verify the exported bytes, including glTF transforms and each part."""
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
    assert cursor == len(data), "Invalid GLB chunk boundaries"
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
        return [struct.unpack_from(fmt, binary, start + i * stride)
                for i in range(a["count"])]

    positions, names, node_names, triangles = [], [], [], 0
    part_positions, part_materials = {}, {}

    def walk(index, parent):
        nonlocal triangles
        node = document["nodes"][index]
        node_names.append(node.get("name"))
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        world = parent @ local
        if "mesh" in node:
            name = node["name"]
            assert name not in part_positions, f"Duplicate mesh node: {name}"
            names.append(name)
            part_positions[name], part_materials[name] = [], set()
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                points = accessor(primitive["attributes"]["POSITION"])
                normals = accessor(primitive["attributes"]["NORMAL"])
                assert len(normals) == len(points), f"Normal count mismatch: {name}"
                assert all(all(math.isfinite(v) for v in normal)
                           and abs(sum(v * v for v in normal) - 1.0) < 1e-4
                           for normal in normals), f"Invalid normals: {name}"
                transformed = [world @ Vector(p) for p in points]
                assert all(math.isfinite(v) for p in transformed for v in p)
                positions.extend(transformed)
                part_positions[name].extend(transformed)
                indices = accessor(primitive["indices"])
                assert len(indices) % 3 == 0, "Incomplete triangle"
                assert all(0 <= index[0] < len(points) for index in indices), "Invalid index"
                triangles += len(indices) // 3
                part_materials[name].add(document["materials"][primitive["material"]]["name"])
        for child in node.get("children", []):
            walk(child, world)

    roots = document["scenes"][document.get("scene", 0)]["nodes"]
    assert len(roots) == 1, "Expected one PineTree root"
    root = document["nodes"][roots[0]]
    assert root.get("name") == "PineTree" and "mesh" not in root
    assert sorted(document["nodes"][i]["name"] for i in root.get("children", [])) == sorted(NAMES)
    for index in roots:
        walk(index, Matrix.Identity(4))
    assert sorted(node_names) == sorted(("PineTree",) + NAMES), node_names
    assert len(document["nodes"]) == len(node_names), "Unexpected unreferenced nodes"
    assert sorted(names) == sorted(NAMES), names
    assert 0 < triangles <= 1500, f"Triangle hard limit exceeded: {triangles}"
    assert triangles <= 1300, f"Triangle target exceeded: {triangles}"

    def bounds(points):
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        return lo, hi, [hi[i] - lo[i] for i in range(3)]

    lo, hi, size = bounds(positions)
    assert all(abs(a - b) <= b * 0.10 for a, b in zip(size, (2.2, 3.6, 2.2))), size
    assert abs(lo[1]) < 1e-6, f"Ground contact moved: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6
    for name, (expected_size, expected_bottom, main_material) in PART_SPECS.items():
        part_lo, _, part_size = bounds(part_positions[name])
        assert all(abs(a - b) < 1e-5 for a, b in zip(part_size, expected_size)), (name, part_size)
        assert abs(part_lo[1] - expected_bottom) < 1e-6, (name, part_lo)
        expected_materials = {main_material}
        if name != "Trunk":
            expected_materials.add("M_leaf_shadow")
        assert part_materials[name] == expected_materials, (name, part_materials[name])
    # Check taper in the exported coordinate system, not only in construction.
    trunk_top = [p for p in part_positions["Trunk"] if abs(p.y - 1.0) < 1e-6]
    assert trunk_top, "Missing trunk top"
    assert abs(max(math.hypot(p.x, p.z) for p in trunk_top) - 0.175) < 1e-6, "Trunk taper moved"
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
        expected = linear_rgba(COLORS[material["name"]])
        assert all(abs(a - b) < 1e-6 for a, b in zip(pbr["baseColorFactor"], expected))
    print(json.dumps({"glb_absolute_path": str(path.resolve()),
                      "file_size_bytes": len(data), "triangle_count": triangles,
                      "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
                      "godot_min_y_m": round(lo[1], 7),
                      "object_names": node_names,
                      "material_names": [m["name"] for m in materials]}, indent=2))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    root = bpy.data.objects.new("PineTree", None)
    bpy.context.scene.collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.25
    parts = [make_trunk(materials["M_trunk"])]
    for name, diameter, height, bottom, color in (
            ("Tier1", 2.2, 1.3, 0.7, "M_leaf_dark"),
            ("Tier2", 1.7, 1.1, 1.6, "M_leaf"),
            ("Tier3", 1.1, 1.0, 2.6, "M_leaf")):
        parts.append(make_tier(name, diameter, height, bottom,
                               materials[color], materials["M_leaf_shadow"]))
    for obj in parts:
        obj.parent = root
        assert obj.location.length < 1e-7, f"Part origin moved: {obj.name}"
        assert all(polygon.use_smooth for polygon in obj.data.polygons), obj.name
    triangle_count = 0
    for obj in parts:
        obj.data.calc_loop_triangles()
        triangle_count += len(obj.data.loop_triangles)
    assert triangle_count == 1248, f"Unexpected construction budget: {triangle_count}"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj == root or obj in parts)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
