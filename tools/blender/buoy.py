"""Create the buoy asset. Run: blender -b --factory-startup -P tools/blender/buoy.py.

Construction coordinates are Godot metres (+Y up); convert them to Blender
(x, -z, y). Only buoy.glb is written. Bobbing and collision belong to the game.
The required 24 x 10 torus has 480 triangles, above the 400 target but below
the authoritative 1,500 hard limit.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/buoy/buoy.glb"
COLORS = {"M_white_warm": "F9F6E5", "M_red": "DD5161"}
MAJOR_SEGMENTS = 24
MINOR_SEGMENTS = 10
MAJOR_RADIUS = 0.3
MINOR_RADIUS = 0.1
SMOOTH_ANGLE = math.radians(40)


def reset_scene():
    # Remove datablocks as well as objects so reruns keep deterministic names.
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


def godot_to_blender(point):
    x, y, z = point
    return (x, -z, y)


def make_ring(materials):
    vertices, faces = [], []
    for i in range(MAJOR_SEGMENTS):
        theta = math.tau * i / MAJOR_SEGMENTS
        for j in range(MINOR_SEGMENTS):
            # Include the bottom and top explicitly: Godot Y spans 0..0.2 m.
            # With ten sides the sampled outer diameter is ~0.79021 m,
            # within the specified 10% tolerance of the ideal 0.8 m torus.
            phi = math.tau * j / MINOR_SEGMENTS - math.pi / 2
            radius = MAJOR_RADIUS + MINOR_RADIUS * math.cos(phi)
            point = (radius * math.cos(theta),
                     MINOR_RADIUS * (1.0 + math.sin(phi)),
                     radius * math.sin(theta))
            vertices.append(godot_to_blender(point))

    def index(i, j):
        return (i % MAJOR_SEGMENTS) * MINOR_SEGMENTS + j % MINOR_SEGMENTS

    for i in range(MAJOR_SEGMENTS):
        for j in range(MINOR_SEGMENTS):
            # Outward winding for a torus parameterized in Godot XZ space.
            faces.append((index(i, j), index(i, j + 1),
                          index(i + 1, j + 1), index(i + 1, j)))

    mesh = bpy.data.meshes.new("RingMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Ring", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(materials["M_white_warm"])
    mesh.materials.append(materials["M_red"])
    for polygon in mesh.polygons:
        major_index = polygon.index // MINOR_SEGMENTS
        # Six major faces per quarter: white, red, white, red, starting +X.
        polygon.material_index = (major_index // (MAJOR_SEGMENTS // 4)) % 2

    # Blender 5.2 Smooth by Angle's underlying sharp-edge representation.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = not edge.is_manifold or edge.calc_face_angle() <= SMOOTH_ANGLE
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.calc_loop_triangles()
    assert len(mesh.vertices) == MAJOR_SEGMENTS * MINOR_SEGMENTS
    assert len(mesh.polygons) == MAJOR_SEGMENTS * MINOR_SEGMENTS
    assert len(mesh.loop_triangles) == 480
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def read_glb(path):
    """Verify the actual exported mesh, materials and transformed Godot bounds."""
    data = path.read_bytes()
    assert struct.unpack_from("<4sII", data) == (b"glTF", 2, len(data))
    cursor, document, binary = 12, None, None
    while cursor < len(data):
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
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride)
                for i in range(a["count"])]

    positions, names, triangles = [], [], 0
    materials = document["materials"]
    quarter_triangles = [0, 0, 0, 0]

    def walk(index, parent):
        nonlocal triangles
        node = document["nodes"][index]
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4]
                            for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        world = parent @ local
        if "mesh" in node:
            names.append(node.get("name", ""))
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                points = [world @ Vector(p)
                          for p in accessor(primitive["attributes"]["POSITION"])]
                positions.extend(points)
                indices = [v[0] for v in accessor(primitive["indices"])]
                assert len(indices) % 3 == 0
                triangles += len(indices) // 3
                material_name = materials[primitive["material"]]["name"]
                for offset in range(0, len(indices), 3):
                    center = sum((points[k] for k in indices[offset:offset + 3]),
                                 Vector()) / 3
                    angle = math.atan2(center.z, center.x) % math.tau
                    quarter = int(angle / (math.pi / 2))
                    expected = "M_white_warm" if quarter % 2 == 0 else "M_red"
                    assert material_name == expected, (quarter + 1, material_name)
                    quarter_triangles[quarter] += 1
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4))
    assert names == ["Ring"], f"Expected only Ring, got: {names}"
    assert triangles <= 1500, f"Triangle hard limit exceeded: {triangles}"
    assert triangles == 480, f"Required 24 x 10 topology changed: {triangles}"
    assert quarter_triangles == [120, 120, 120, 120], quarter_triangles
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert all(abs(a - b) <= b * 0.1 + 1e-7
               for a, b in zip(size, (0.8, 0.2, 0.8))), size
    assert abs(lo[1]) < 1e-7, f"Bottom must be at Godot Y = 0: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6
    assert not document.get("cameras") and not document.get("textures")
    assert not document.get("animations")
    assert "KHR_lights_punctual" not in document.get("extensions", {})
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
                      "object_names": names,
                      "material_names": [m["name"] for m in materials]}))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    ring = make_ring(materials)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj == ring)
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
