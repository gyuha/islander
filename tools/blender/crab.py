"""Create the clay crab. Run: blender -b --factory-startup -P tools/blender/crab.py.

Construction coordinates below are metres in Godot space: +Y up, +Z front,
and the crab's left is +X. Convert to Blender (x, -z, y) only when making
objects. Mesh coordinates are relative to the five animation pivots.
No Blender run or preview is required to author this script.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/crab/crab.glb"
PIVOTS = {
    "Body": (0.0, 0.12, 0.0),
    "ClawL": (0.28, 0.24, 0.15),
    "ClawR": (-0.28, 0.24, 0.15),
    "LegsL": (0.26, 0.20, 0.0),
    "LegsR": (-0.26, 0.20, 0.0),
}
COLORS = {
    "M_crab": "E0573A",
    "M_cream": "F2E7BB",
    "M_rust": "8C341F",
    "M_white_warm": "F9F6E5",
    "M_ink": "2B2233",
}
SMOOTH_ANGLE = math.radians(40)


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


def blender_coords(p):
    return Vector((p[0], -p[2], p[1]))


class MeshBuilder:
    """Accumulate overlapping clay solids into one mesh per animated part.

    Closed solids intentionally intersect at joints, avoiding boolean slivers
    and retaining the small, deterministic triangle budget.
    """

    def __init__(self):
        self.vertices = []
        self.faces = []
        self.material_indices = []

    def vertex(self, p):
        self.vertices.append(Vector(p))
        return len(self.vertices) - 1

    def face(self, indices, material):
        self.faces.append(tuple(indices))
        self.material_indices.append(tuple(COLORS).index(material))

    def bridge(self, a, b, material):
        for i in range(len(a)):
            j = (i + 1) % len(a)
            self.face((a[i], a[j], b[j], b[i]), material)

    def ellipsoid(self, center, radii, material, sectors=12, stacks=6):
        center = Vector(center)
        top = self.vertex(center + Vector((0, radii[1], 0)))
        rings = []
        for j in range(1, stacks):
            theta = math.pi * j / stacks
            ring = []
            for i in range(sectors):
                phi = math.tau * i / sectors
                ring.append(self.vertex(center + Vector((
                    radii[0] * math.sin(theta) * math.cos(phi),
                    radii[1] * math.cos(theta),
                    radii[2] * math.sin(theta) * math.sin(phi)))))
            rings.append(ring)
        bottom = self.vertex(center - Vector((0, radii[1], 0)))
        for i in range(sectors):
            j = (i + 1) % sectors
            self.face((top, rings[0][i], rings[0][j]), material)
            self.face((bottom, rings[-1][j], rings[-1][i]), material)
        for a, b in zip(rings, rings[1:]):
            self.bridge(a, b, material)

    def capsule(self, start, end, radius, material, sectors=10, ground=False):
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        reference = Vector((0, 0, 1))
        if abs(axis.dot(reference)) > 0.9:
            reference = Vector((0, 1, 0))
        u = axis.cross(reference).normalized()
        v = axis.cross(u).normalized()

        def point(p):
            # A small planar sole and outer foot edge, never geometry below 0.
            if ground:
                p.y = max(0.0, p.y)
                p.x = min(0.5, max(-0.5, p.x))
            return self.vertex(p)

        pole_a = point(start - axis * radius)
        rings = []
        d = radius / math.sqrt(2)
        for center, r in ((start - axis * d, d), (start, radius),
                          (end, radius), (end + axis * d, d)):
            rings.append([point(center + r * (
                u * math.cos(math.tau * i / sectors)
                + v * math.sin(math.tau * i / sectors))) for i in range(sectors)])
        pole_b = point(end + axis * radius)
        for i in range(sectors):
            j = (i + 1) % sectors
            self.face((pole_a, rings[0][j], rings[0][i]), material)
            self.face((pole_b, rings[-1][i], rings[-1][j]), material)
        for a, b in zip(rings, rings[1:]):
            self.bridge(a, b, material)

    def cylinder(self, x, z, bottom, top, radius, material, sectors=10):
        # Three rings give the short eye stalk a subtly inflated clay profile.
        rings = []
        for y, r in ((bottom, radius), ((bottom + top) / 2, radius * 1.05),
                     (top, radius)):
            rings.append([self.vertex((x + r * math.cos(math.tau * i / sectors),
                                       y, z + r * math.sin(math.tau * i / sectors)))
                          for i in range(sectors)])
        self.face(reversed(rings[0]), material)
        self.face(rings[-1], material)
        for a, b in zip(rings, rings[1:]):
            self.bridge(a, b, material)

    def finish(self, name, materials, root):
        pivot = Vector(PIVOTS[name])
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata([blender_coords(p - pivot) for p in self.vertices], [], self.faces)
        mesh.update()
        for material in materials.values():
            mesh.materials.append(material)
        for polygon, material_index in zip(mesh.polygons, self.material_indices):
            polygon.material_index = material_index
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        # Same Smooth by Angle 40-degree sharp-edge representation as rock.py.
        for edge in bm.edges:
            edge.smooth = not edge.is_manifold or edge.calc_face_angle() <= SMOOTH_ANGLE
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent = root
        obj.location = blender_coords(pivot)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        # Preserve the node translation: the origin is the animation pivot.
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.select_set(False)
        mesh.calc_loop_triangles()
        return obj


def make_body():
    mesh = MeshBuilder()
    sectors = 24
    rings = []
    # A .64 x .315 x .47 dome: the small cream base rolls into a broad
    # belly, while the upper rings retain volume almost to the crown.
    for y, rx, rz in ((0.120, 0.200, 0.150), (0.130, 0.250, 0.185),
                      (0.155, 0.290, 0.215), (0.205, 0.320, 0.235),
                      (0.290, 0.307, 0.225), (0.365, 0.265, 0.195),
                      (0.415, 0.180, 0.132), (0.430, 0.090, 0.066)):
        rings.append([mesh.vertex((rx * math.cos(math.tau * i / sectors), y,
                                    rz * math.sin(math.tau * i / sectors)))
                      for i in range(sectors)])
    mesh.face(reversed(rings[0]), "M_cream")
    for j, (a, b) in enumerate(zip(rings, rings[1:])):
        mesh.bridge(a, b, "M_cream" if j < 2 else "M_crab")
    top = mesh.vertex((0, 0.435, 0))
    for i in range(sectors):
        mesh.face((rings[-1][i], rings[-1][(i + 1) % sectors], top), "M_crab")
    for x in (-0.125, 0.125):
        mesh.cylinder(x, 0.17, 0.31, 0.44, 0.02, "M_crab")
        mesh.ellipsoid((x, 0.48, 0.17), (0.05, 0.05, 0.05), "M_white_warm")
        # Face +Z. The pupil's perimeter sits within the curved sclera.
        mesh.ellipsoid((x, 0.482, 0.214), (0.021, 0.026, 0.011),
                       "M_ink", sectors=10, stacks=4)
    mouth = ((-0.033, 0.285, 0.228), (-0.022, 0.270, 0.232),
             (0, 0.263, 0.234), (0.022, 0.270, 0.232), (0.033, 0.285, 0.228))
    # Four short overlapping rounded strokes form a shallow, friendly U.
    for a, b in zip(mouth, mouth[1:]):
        mesh.capsule(a, b, 0.004, "M_ink", sectors=6)
    return mesh


def make_claw(side):
    mesh = MeshBuilder()
    mesh.capsule((side * 0.28, 0.24, 0.15), (side * 0.335, 0.22, 0.215),
                 0.070, "M_crab", sectors=10)
    # Each pincer occupies about .26 x .20 x .22. Broad jaw roots overlap
    # the palm, then separate into a V with fat, hemispherical ends.
    mesh.ellipsoid((side * 0.35, 0.22, 0.23), (0.13, 0.10, 0.05), "M_crab")
    sectors = 10
    for jaw in (-1, 1):
        rings = []
        for x, z, dy, rx, ry in ((0.350, 0.225, 0.030, 0.130, 0.065),
                                 (0.365, 0.280, 0.040, 0.115, 0.060),
                                 (0.395, 0.330, 0.060, 0.080, 0.040),
                                 (0.425, 0.365, 0.068, 0.045, 0.030),
                                 (0.435, 0.385, 0.065, 0.025, 0.025)):
            y = 0.22 + jaw * dy
            rings.append([mesh.vertex((side * (x + rx * math.cos(math.tau * i / sectors)),
                                        y + ry * math.sin(math.tau * i / sectors), z))
                          for i in range(sectors)])
        mesh.face(reversed(rings[0]), "M_crab")
        for j, (a, b) in enumerate(zip(rings, rings[1:])):
            mesh.bridge(a, b, "M_rust" if j >= 3 else "M_crab")
        tip = mesh.vertex((side * 0.435, 0.22 + jaw * 0.065, 0.40))
        for i in range(sectors):
            mesh.face((rings[-1][i], rings[-1][(i + 1) % sectors], tip), "M_rust")
    return mesh


def make_legs(side):
    mesh = MeshBuilder()
    # Roots occupy the specified z positions; the rear leg fans backwards to
    # balance the forward claws and give the whole crab its .75 m depth.
    for z, knee_z, foot_z in ((0.12, 0.13, 0.12), (0.0, -0.06, -0.10),
                              (-0.12, -0.265, -0.345)):
        hip = (side * 0.26, 0.20, z)
        knee = (side * 0.415, 0.145, knee_z)
        foot = (side * 0.485, 0.035, foot_z)
        mesh.capsule(hip, knee, 0.045, "M_crab")
        mesh.capsule(knee, foot, 0.045, "M_crab", ground=True)
    return mesh


def read_glb(path):
    """Verify actual exported vertices, hierarchy, pivots, and materials."""
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

    positions, pivots, object_names, points_by_name, parents = [], {}, [], {}, {}
    triangles = 0
    nodes = document["nodes"]

    def walk(index, parent_world, parent_name=None):
        nonlocal triangles
        node = nodes[index]
        name = node.get("name", "")
        assert name not in object_names, f"Duplicate node: {name}"
        object_names.append(name)
        parents[name] = parent_name
        if "matrix" in node:
            local = Matrix([node["matrix"][i:i + 4] for i in range(0, 16, 4)]).transposed()
        else:
            q = node.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                       Quaternion((q[3], q[0], q[1], q[2])),
                                       Vector(node.get("scale", [1, 1, 1])))
        world = parent_world @ local
        if name in PIVOTS:
            pivots[name] = list(world.translation)
        if "mesh" in node:
            assert name in PIVOTS, f"Unexpected mesh (including collision): {name}"
            points_by_name[name] = []
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], f"Missing normals: {name}"
                points = [world @ Vector(p) for p in accessor(primitive["attributes"]["POSITION"])]
                positions.extend(points)
                points_by_name[name].extend(points)
                count = (len(accessor(primitive["indices"])) if "indices" in primitive
                         else len(points))
                assert count % 3 == 0, "Incomplete triangle"
                triangles += count // 3
        for child in node.get("children", []):
            walk(child, world, name)

    scene_roots = document["scenes"][document.get("scene", 0)]["nodes"]
    for index in scene_roots:
        walk(index, Matrix.Identity(4))
    assert sorted(object_names) == sorted(("Crab", *PIVOTS)), object_names
    assert set(points_by_name) == set(PIVOTS), "The five named parts must be meshes"
    root = next(n for n in nodes if n.get("name") == "Crab")
    assert "mesh" not in root and parents["Crab"] is None, "Crab must be the root Empty"
    assert len(scene_roots) == 1 and len(root.get("children", [])) == 5, "Invalid hierarchy"
    for name, expected in PIVOTS.items():
        assert parents[name] == "Crab", f"Incorrect parent: {name}"
        assert all(abs(a - b) <= 0.01 for a, b in zip(pivots[name], expected)), (name, pivots[name])
    assert all(abs(v) < 1e-7 for v in root.get("translation", [0, 0, 0])), "Root moved"
    lo = [min(p[i] for p in positions) for i in range(3)]
    hi = [max(p[i] for p in positions) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert triangles <= 3000, f"Hard triangle limit exceeded: {triangles}"
    assert all(abs(a - b) <= b * 0.10 for a, b in zip(size, (1.0, 0.5, 0.75))), size
    assert abs(lo[1]) < 1e-6, f"Ground contact moved: {lo[1]}"
    assert hi[1] <= 0.55 + 1e-6, f"Shell or eye tips too high: {hi[1]}"
    for name in ("LegsL", "LegsR"):
        points = points_by_name[name]
        # Separate bands around the three feet prove all six soles touch y=0.
        for foot_z in (0.12, -0.10, -0.345):
            sole = [p for p in points if abs(p.z - foot_z) < 0.04 and abs(p.x) > 0.46]
            assert sole and min(p.y for p in sole) < 1e-6, f"Foot not grounded: {name}, {foot_z}"
    for name, side in (("ClawL", 1), ("ClawR", -1)):
        points = points_by_name[name]
        tip = max(p.z for p in points)
        assert abs(tip - 0.40) < 0.01, f"Claw tip not facing +Z: {name}"
        assert tip - pivots[name][2] > 0.20, f"Claw does not extend forwards: {name}"
        tips = [p for p in points if p.z > tip - 0.002]
        assert tips and all(abs(p.x - side * 0.435) < 0.01 for p in tips), name
        assert max(side * p.x for p in tips) > side * pivots[name][0] + 0.15, name
    assert not document.get("cameras") and not document.get("textures") and not document.get("images")
    assert not document.get("animations"), "Unexpected animation"
    assert "KHR_lights_punctual" not in document.get("extensions", {})
    materials = document["materials"]
    assert len(materials) <= 6 and sorted(m["name"] for m in materials) == sorted(COLORS)
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
                      "object_names": object_names,
                      "material_names": [m["name"] for m in materials],
                      "pivots": {name: [round(v, 7) for v in pivots[name]] for name in PIVOTS}}))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    root = bpy.data.objects.new("Crab", None)
    bpy.context.scene.collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.1
    builders = {"Body": make_body(), "ClawL": make_claw(1), "ClawR": make_claw(-1),
                "LegsL": make_legs(1), "LegsR": make_legs(-1)}
    objects = [builder.finish(name, materials, root) for name, builder in builders.items()]
    triangles = sum(len(obj.data.loop_triangles) for obj in objects)
    assert triangles <= 2800, f"Construction exceeded the triangle target: {triangles}"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj == root or obj in objects)
    bpy.context.view_layer.objects.active = root
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
