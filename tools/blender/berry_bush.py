"""Create the clay berry bush with Blender 5.2.

Run: blender -b --factory-startup -P tools/blender/berry_bush.py
Metres, Blender Z up; glTF/Godot maps (x, y, z) to (x, z, -y).
The bottom centre is the origin and Blender -Y is the front.
Only berry_bush.glb is written. No textures, collision, or blend file.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/berry_bush/berry_bush.glb"
NAMES = ("Leaves", "Berries")
COLORS = {"M_leaf": "3FA463", "M_grass_light": "79C46A", "M_red": "DD5161"}
SMOOTH_ANGLE = math.radians(40)
BERRY_DIAMETER = 0.14
TRIANGLE_TARGET = 800
TRIANGLE_LIMIT = 1500


def reset_scene():
    # Remove datablocks rather than only unlinking objects, including on reruns.
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


def sphere_geometry(sectors, latitudes, center, radii, flat_bottom=False):
    """Closed UV sphere; optional clipping replaces the south pole with a foot.

    Fit the sampled horizontal extents to the requested radii, so a sparse
    longitude ring does not silently shrink the specified bounding box.
    """
    vertices = [Vector((math.sin(theta) * math.cos(math.tau * i / sectors),
                        math.sin(theta) * math.sin(math.tau * i / sectors),
                        math.cos(theta)))
                for theta in latitudes for i in range(sectors)]
    vertices.append(Vector((0, 0, 1)))
    top = len(vertices) - 1
    if not flat_bottom:
        vertices.append(Vector((0, 0, -1)))
    for axis in (0, 1):
        extent = max(abs(v[axis]) for v in vertices)
        for v in vertices:
            v[axis] /= extent
    for v in vertices:
        for axis in range(3):
            v[axis] = center[axis] + v[axis] * radii[axis]
        if flat_bottom:
            v.z = max(0.0, v.z)
    faces = [(top, i, (i + 1) % sectors) for i in range(sectors)]
    for ring in range(len(latitudes) - 1):
        a, b = ring * sectors, (ring + 1) * sectors
        for i in range(sectors):
            nxt = (i + 1) % sectors
            faces.append((a + i, b + i, b + nxt, a + nxt))
    last = (len(latitudes) - 1) * sectors
    if flat_bottom:
        assert all(abs(vertices[last + i].z) < 1e-8 for i in range(sectors))
        faces.append(tuple(last + i for i in reversed(range(sectors))))
    else:
        bottom = len(vertices) - 1
        faces.extend((last + i, bottom, last + (i + 1) % sectors)
                     for i in range(sectors))
    return vertices, faces


def append_geometry(vertices, faces, additions):
    offset = len(vertices)
    new_vertices, new_faces = additions
    vertices.extend(new_vertices)
    faces.extend(tuple(offset + i for i in face) for face in new_faces)


def make_mesh(name, vertices, faces, materials, face_materials):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    assert len(face_materials) == len(mesh.polygons)
    for polygon, index in zip(mesh.polygons, face_materials):
        polygon.material_index = index
    # Same Smooth by Angle representation as rock.py, without a GN dependency.
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
    # Coordinates are baked into the mesh. Both object origins stay at ground 0.
    assert obj.location.length == 0
    return obj


def make_leaves(materials):
    vertices, faces, face_materials = [], [], []
    # One high crown, four lower overlapping lobes. Cardinal lobes set the
    # overall footprint to exactly 1 x 1 m; every lobe has a closed flat foot.
    lumps = [((0, 0, 0.34), (0.34, 0.34, 0.46), 12, (30, 60, 90, 120, 150)),
             ((-0.23, 0, 0.25), (0.27, 0.27, 0.32), 10, (36, 72, 108, 144)),
             ((0.23, 0, 0.25), (0.27, 0.27, 0.32), 10, (36, 72, 108, 144)),
             ((0, -0.23, 0.25), (0.27, 0.27, 0.32), 10, (36, 72, 108, 144)),
             ((0, 0.23, 0.25), (0.27, 0.27, 0.32), 10, (36, 72, 108, 144))]
    for index, (center, radii, sectors, angles) in enumerate(lumps):
        geometry = sphere_geometry(sectors, tuple(map(math.radians, angles)),
                                   center, radii, flat_bottom=True)
        local_vertices, local_faces = geometry
        for face in local_faces:
            height = sum(local_vertices[i].z for i in face) / len(face)
            face_materials.append(1 if index == 0 and height > 0.63 else 0)
        append_geometry(vertices, faces, geometry)
    return make_mesh("Leaves", vertices, faces,
                     [materials["M_leaf"], materials["M_grass_light"]], face_materials)


def make_berries(leaves, material):
    mesh = leaves.data
    mesh.calc_loop_triangles()
    tree = BVHTree.FromPolygons([v.co for v in mesh.vertices],
                               [tuple(t.vertices) for t in mesh.loop_triangles],
                               all_triangles=True)
    vertices, faces, centers = [], [], []
    # Front three, front shoulder pair, three around the sides/back, one high.
    # Ray casts hit the actual outside of the overlapping lobes, not an
    # imaginary enclosing sphere. A berry centre on that surface embeds half.
    placements = ((-155, 22), (-90, 18), (-25, 22), (-130, 45), (-50, 45),
                  (25, 28), (100, 24), (165, 28), (70, 58))
    focus = Vector((0, 0, 0.34))
    for azimuth, elevation in placements:
        a, e = math.radians(azimuth), math.radians(elevation)
        direction = Vector((math.cos(a) * math.cos(e),
                            math.sin(a) * math.cos(e), math.sin(e)))
        hit, normal, _, _ = tree.ray_cast(focus + direction * 2, -direction, 3)
        assert hit is not None, f"Berry missed the leaves: {azimuth}, {elevation}"
        assert normal.dot(direction) > 0, "Berry hit an inward-facing leaf"
        assert all((hit - center).length > BERRY_DIAMETER for center in centers)
        centers.append(hit.copy())
        append_geometry(vertices, faces,
                        sphere_geometry(10, tuple(map(math.radians, (36, 72, 108, 144))),
                                        hit, (BERRY_DIAMETER / 2,) * 3))
    assert len(centers) == 9
    # Directly concatenate nine disconnected spheres into ONE mesh/object.
    # There are no separate berry nodes that could survive a visibility toggle.
    return make_mesh("Berries", vertices, faces, [material], [0] * len(faces))


def component_bounds(points, triangles):
    """Weld glTF normal/material seam duplicates before counting sphere islands."""
    keys = [tuple(round(c, 6) for c in p) for p in points]
    neighbors = {key: set() for key in keys}
    for triangle in triangles:
        a, b, c = (keys[i] for i in triangle)
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    bounds = []
    while neighbors:
        seed = next(iter(neighbors))
        stack, island = [seed], []
        while stack:
            key = stack.pop()
            if key not in neighbors:
                continue
            island.append(key)
            stack.extend(neighbors.pop(key))
        bounds.append(([min(p[i] for p in island) for i in range(3)],
                       [max(p[i] for p in island) for i in range(3)]))
    return bounds


def read_glb(path):
    """Verify exported bytes and transformed glTF geometry, not scene estimates."""
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
    assert document is not None and binary is not None

    def accessor(index):
        a = document["accessors"][index]
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride) for i in range(a["count"])]

    positions, names, triangle_count, islands = [], [], 0, {}

    def walk(index, parent):
        nonlocal triangle_count
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
            name = node["name"]
            names.append(name)
            assert (world @ Vector((0, 0, 0))).length < 1e-6, name
            points, triangles = [], []
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                local_points = accessor(primitive["attributes"]["POSITION"])
                indices = [item[0] for item in accessor(primitive["indices"])]
                assert len(indices) % 3 == 0
                offset = len(points)
                points.extend(world @ Vector(p) for p in local_points)
                triangles.extend(tuple(offset + v for v in indices[i:i + 3])
                                 for i in range(0, len(indices), 3))
            positions.extend(points)
            triangle_count += len(triangles)
            islands[name] = component_bounds(points, triangles)
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4))
    assert sorted(names) == sorted(NAMES), names
    assert len(document["nodes"]) == 2, "Unexpected helper or collision nodes"
    assert len(islands["Leaves"]) == 5, "Leaves must contain five sphere lobes"
    assert len(islands["Berries"]) == 9, "Berries must contain exactly nine spheres"
    for low, high in islands["Berries"]:
        assert all(abs(high[i] - low[i] - BERRY_DIAMETER) < 1e-5
                   for i in range(3)), (low, high)
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert 0 < triangle_count <= TRIANGLE_LIMIT, triangle_count
    assert all(abs(actual - wanted) <= wanted * 0.10 + 1e-6
               for actual, wanted in zip(size, (1.0, 0.8, 1.0))), size
    assert abs(lo[1]) < 1e-7, f"Ground contact moved: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6, (lo, hi)
    assert not document.get("textures") and not document.get("images")
    assert not document.get("cameras") and not document.get("animations")
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
    print(json.dumps({"glb_absolute_path": str(path.resolve()),
                      "file_size_bytes": len(data), "triangle_count": triangle_count,
                      "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
                      "godot_min_y_m": round(lo[1], 7), "object_names": names,
                      "material_names": [m["name"] for m in materials]}, indent=2))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    leaves = make_leaves(materials)
    make_berries(leaves, materials["M_red"])
    # 430 leaf triangles + 9 * 80 berry triangles = 1,150. The 800 target is
    # soft; retain rounded silhouettes within the authoritative 1,500 limit.
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
