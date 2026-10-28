"""Create the clay rock asset. Run: blender -b -P tools/blender/rock.py.

All construction is in metres, Blender Z up. The exporter maps (x, y, z)
to Godot/glTF (x, z, -y), so the front attachment is on Blender -Y.
Only this repository's rock.glb is written; no blend file is needed.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector, noise
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/rock/rock.glb"
NAMES = ("RockBody", "RockSmall", "Moss")
COLORS = {"M_stone": "9BA7A6", "M_stone_light": "C4CDCB", "M_grass": "5DB85E"}
SMOOTH_ANGLE = math.radians(40)


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


def make_mesh(name, vertices, faces, material):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(material)
    # Blender 5.2 Smooth by Angle's underlying sharp-edge representation.
    # Every polygon remains smooth; only normal discontinuities >40 deg split.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = not edge.is_manifold or edge.calc_face_angle() <= SMOOTH_ANGLE
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)
    return obj


def make_lump(name, sectors, latitudes, size, center_xy, material, seed):
    """Latitude-subdivided sphere, softly distorted and clipped to a flat foot.

    The sole noise wavelength is 0.9 m, well above the 0.5 m minimum.
    Latitude spacing reserves geometry for the rounded shoulder and foot.
    """
    vertices = []
    for theta in latitudes:
        for i in range(sectors):
            phi = math.tau * i / sectors
            p = Vector((0.6 * math.sin(theta) * math.cos(phi),
                        0.5 * math.sin(theta) * math.sin(phi),
                        0.4 * math.cos(theta)))
            d = noise.noise_vector(p / 0.9 + Vector((seed, 2.3, -1.7)))
            p += d * 0.024
            vertices.append(p)
    vertices.append(Vector((0.0, 0.0, 0.4)))
    pole = len(vertices) - 1
    lo_z = min(v.z for v in vertices)
    hi_z = max(v.z for v in vertices)
    # A broad, gently leaning summit keeps the silhouette hand-shaped.
    for index, p in enumerate(vertices):
        u = (p.z - lo_z) / (hi_z - lo_z)
        p.x += 0.10 * u * u
        p.y -= 0.07 * u * u
        if index < sectors:
            p.z = lo_z
    bounds = [(min(v[a] for v in vertices), max(v[a] for v in vertices)) for a in range(3)]
    for p in vertices:
        for a in range(3):
            low, high = bounds[a]
            p[a] = (p[a] - low) / (high - low) * size[a]
        p.x += center_xy[0] - size[0] / 2
        p.y += center_xy[1] - size[1] / 2
    faces = [tuple(reversed(range(sectors)))]
    for j in range(len(latitudes) - 1):
        for i in range(sectors):
            nxt = (i + 1) % sectors
            faces.append((j * sectors + i, j * sectors + nxt,
                          (j + 1) * sectors + nxt, (j + 1) * sectors + i))
    last = (len(latitudes) - 1) * sectors
    faces += [(last + i, last + (i + 1) % sectors, pole) for i in range(sectors)]
    return make_mesh(name, vertices, faces, material)


def make_moss(body, material):
    """A closed 8 mm shell, its visible surface 2 cm above the stone.

    Ray sampling follows the actual low-resolution stone surface. The patch
    area is fitted to 25% of the upward-facing body area, excluding the foot.
    This shoulder placement also leaves the body's summit at exactly 0.8 m.
    """
    mesh = body.data
    mesh.calc_loop_triangles()
    tree = BVHTree.FromPolygons([v.co for v in mesh.vertices],
                               [tuple(t.vertices) for t in mesh.loop_triangles],
                               all_triangles=True)
    upper_area = sum(p.area for p in mesh.polygons if p.normal.z > 0.01)
    segments = 12
    center = Vector((-0.285, 0.145, 0))

    def sample(scale):
        coords = [center.copy()]
        for radius in (0.52, 1.0):
            for i in range(segments):
                a = math.tau * i / segments
                # Two broad lobes, no fine noise or serrated leaf-like edges.
                rim = 1.0 + 0.045 * math.sin(2 * a + 0.6)
                coords.append(center + Vector((math.cos(a) * 0.25 * radius * scale * rim,
                                                math.sin(a) * 0.28 * radius * scale * rim, 0)))
        surface = []
        for p in coords:
            hit, normal, _, _ = tree.ray_cast(Vector((p.x, p.y, 2)), Vector((0, 0, -1)))
            if hit is None:
                return None
            surface.append((hit, normal))
        return surface

    faces = []
    for i in range(segments):
        nxt = (i + 1) % segments
        faces.append((0, 1 + i, 1 + nxt))
        faces.append((1 + i, 13 + i, 13 + nxt, 1 + nxt))

    def area(surface):
        total = 0.0
        for face in faces:
            a = surface[face[0]][0]
            for i in range(1, len(face) - 1):
                b, c = surface[face[i]][0], surface[face[i + 1]][0]
                total += (b - a).cross(c - a).length / 2
        return total

    low, high = 0.5, 1.18
    for _ in range(32):
        scale = (low + high) / 2
        surface = sample(scale)
        if surface is None or area(surface) > upper_area * 0.25:
            high = scale
        else:
            low = scale
    surface = sample(low)
    # A narrower bottom rim softens the tiny edge without box-like geometry.
    verts = [hit + normal * 0.02 for hit, normal in surface]
    verts += [hit + normal * 0.012 for hit, normal in surface]
    count = len(surface)
    shell_faces = list(faces)
    shell_faces += [tuple(count + i for i in reversed(face)) for face in faces]
    for i in range(segments):
        a, b = 13 + i, 13 + (i + 1) % segments
        shell_faces.append((a, count + a, count + b, b))
    obj = make_mesh("Moss", verts, shell_faces, material)
    print(f"Moss top coverage: {area(surface) / upper_area:.2%}; surface offset: 0.020 m")
    return obj


def read_glb(path):
    """Verify exported geometry, including glTF node transforms, from bytes."""
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

    def accessor(index):
        a = document["accessors"][index]
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride) for i in range(a["count"])]

    positions, names, triangles = [], [], 0

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
        if "mesh" in node:
            names.append(node["name"])
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                points = accessor(primitive["attributes"]["POSITION"])
                positions.extend(world @ Vector(p) for p in points)
                triangles += len(accessor(primitive["indices"])) // 3
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4))
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert sorted(names) == sorted(NAMES), names
    assert triangles <= 400, f"Triangle target exceeded: {triangles}"
    assert all(abs(a - b) < 1e-5 for a, b in zip(size, (1.2, 0.8, 1.0))), size
    assert abs(lo[1]) < 1e-7, f"Ground contact moved: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6
    assert not document.get("cameras") and not document.get("textures")
    assert "KHR_lights_punctual" not in document.get("extensions", {})
    materials = document["materials"]
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
                      "material_names": [m["name"] for m in materials]}, indent=2))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    body = make_lump("RockBody", 14, (2.52, 2.22, 1.83, 1.41, 1.00, 0.61, 0.28),
                     (1.2, 1.0, 0.8), (0, 0), materials["M_stone"], 1.7)
    make_lump("RockSmall", 10, (2.52, 2.02, 1.43, 0.86, 0.34),
              (0.45, 0.4, 0.35), (0.375, -0.295), materials["M_stone_light"], 5.2)
    make_moss(body, materials["M_grass"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj.type == "MESH")
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
