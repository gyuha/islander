"""Create the clay boat. Run: blender -b --factory-startup -P tools/blender/boat.py.

Construction coordinates are Godot metres, Y up, bow +Z. Conversion to
Blender is (x, -z, y); the glTF exporter maps this back to (x, y, z).
The reported bounding box is Hull only: the projecting oar is excluded.
Only assets/models/boat/boat.glb is written; no blend file is needed.
"""

import json
import math
from pathlib import Path
import struct

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/models/boat/boat.glb"
NAMES = ("Hull", "Seat", "Oars")
COLORS = {
    "M_earth": "C36F46",
    "M_earth_dark": "985033",
    "M_wood_light": "BE946D",
    "M_wood_dark": "876C46",
}
SMOOTH_ANGLE = math.radians(40)
WALL_THICKNESS = 0.08

# Clockwise in Godot's XZ plane. The stern has a broad, flat central edge;
# the +Z bow has a rounded, narrower nose. Arc spacing keeps turns below 40°.
STARBOARD = (
    (0.20, 1.26), (0.36, 1.13), (0.46, 0.92), (0.55, 0.25),
    (0.55, -0.35), (0.51, -0.85), (0.41, -1.18), (0.22, -1.30),
)
OUTLINE = ((0.0, 1.30),) + STARBOARD + ((0.0, -1.30),) + tuple(
    (-x, z) for x, z in reversed(STARBOARD)
)


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


def smooth_by_angle(mesh):
    # Blender 5.2 Smooth by Angle's underlying sharp-edge representation.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    assert all(edge.is_manifold for edge in bm.edges), "Mesh must be closed"
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = edge.calc_face_angle() <= SMOOTH_ANGLE
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


class Geometry:
    """Accumulate disconnected closed parts into one named mesh."""

    def __init__(self):
        self.vertices = []
        self.faces = []
        self.material_indices = []

    def ring(self, points):
        start = len(self.vertices)
        self.vertices.extend(points)
        return tuple(range(start, len(self.vertices)))

    def face(self, indices, material=0):
        self.faces.append(tuple(indices))
        self.material_indices.append(material)

    def bridge(self, first, second, material=0):
        assert len(first) == len(second)
        for i in range(len(first)):
            nxt = (i + 1) % len(first)
            self.face((first[i], first[nxt], second[nxt], second[i]), material)

    def object(self, name, materials):
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata([(x, -z, y) for x, y, z in self.vertices], [], self.faces)
        for material in materials:
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, self.material_indices):
            polygon.material_index = index
        mesh.update()
        smooth_by_angle(mesh)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.select_set(False)
        return obj


def inset_polygon(points, distance):
    """Offset clockwise convex edges inward by an exact perpendicular distance."""
    result = []
    for i, point in enumerate(points):
        previous, following = points[i - 1], points[(i + 1) % len(points)]
        normals = []
        for a, b in ((previous, point), (point, following)):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dz)
            normals.append((dz / length, -dx / length))
        a, b = normals
        denominator = 1.0 + a[0] * b[0] + a[1] * b[1]
        result.append((point[0] + distance * (a[0] + b[0]) / denominator,
                       point[1] + distance * (a[1] + b[1]) / denominator))
    return result


def make_hull(materials):
    geometry = Geometry()

    def side_inset(y):
        return 0.105 * (0.52 - y) / (0.52 - 0.14)

    # (height, inward offset, material of strip arriving at this ring).
    # The narrow dark strips subdivide a straight surface: no raised planks,
    # grooves, floating overlays, textures, or extra materials.
    profile = [(0.0, 0.26, 0), (0.035, 0.17, 0), (0.14, 0.105, 0)]
    for y, material in ((0.24, 0), (0.258, 1), (0.38, 0), (0.398, 1),
                        (0.52, 0), (0.56, 0)):
        profile.append((y, side_inset(y) if y <= 0.52 else 0.0, material))

    # A continuous 8 cm gunwale, crowned by a 4 cm radius semicircle.
    # Six segments give 30° turns, which remain smooth at the 40° threshold.
    radius = WALL_THICKNESS / 2
    for step in range(1, 7):
        angle = math.pi * step / 6
        profile.append((0.56 + radius * math.sin(angle),
                        radius * (1.0 - math.cos(angle)), 1))
    profile.extend(((0.52, WALL_THICKNESS, 2),
                    (0.14, 0.105 + WALL_THICKNESS, 2), (0.08, 0.26, 2)))

    rings = []
    for height, inset, material in profile:
        ring = geometry.ring((x, height, z) for x, z in inset_polygon(OUTLINE, inset))
        if rings:
            geometry.bridge(rings[-1], ring, material)
        rings.append(ring)
    geometry.face(tuple(reversed(rings[0])), 0)
    # Only the low interior floor is capped. The opening at the gunwale is empty.
    geometry.face(rings[-1], 2)
    return geometry.object("Hull", [materials[name] for name in
                                   ("M_earth", "M_earth_dark", "M_wood_light")])


def half_width_at(z, inset):
    points = inset_polygon(OUTLINE, inset)
    hits = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        if min(a[1], b[1]) <= z <= max(a[1], b[1]) and abs(b[1] - a[1]) > 1e-9:
            hits.append(a[0] + (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]))
    assert hits, f"No hull section at z={z}"
    return max(hits)


def make_seats(material):
    geometry = Geometry()
    center_y, thickness = 0.43, 0.06
    inner_inset = 0.105 * (0.52 - center_y) / 0.38 + WALL_THICKNESS
    for z in (0.4, -0.4):
        # Board ends embed slightly into the walls to read as supported seats.
        half_width = half_width_at(z, inner_inset) + 0.015
        bottom = geometry.ring((x, center_y - thickness / 2, zz)
                               for x, zz in ((-half_width, z - 0.10),
                                             (half_width, z - 0.10),
                                             (half_width, z + 0.10),
                                             (-half_width, z + 0.10)))
        top = geometry.ring((geometry.vertices[i][0], center_y + thickness / 2,
                             geometry.vertices[i][2]) for i in bottom)
        geometry.bridge(bottom, top)
        geometry.face(tuple(reversed(bottom)))
        geometry.face(top)
    obj = geometry.object("Seat", [material])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bevel = obj.modifiers.new("Soft board edges", "BEVEL")
    bevel.width = thickness * 0.12
    bevel.segments = 2
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(30)
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    smooth_by_angle(obj.data)
    obj.select_set(False)
    return obj


def rim_crossing(start_xz, direction_xz, inset=WALL_THICKNESS / 2):
    """Distance parameter along a ray to the rim centre or its outer edge."""
    def cross(a, b):
        return a[0] * b[1] - a[1] * b[0]

    points = inset_polygon(OUTLINE, inset)
    hits = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        edge = (b[0] - a[0], b[1] - a[1])
        delta = (a[0] - start_xz[0], a[1] - start_xz[1])
        denominator = cross(direction_xz, edge)
        if abs(denominator) < 1e-9:
            continue
        t = cross(delta, edge) / denominator
        u = cross(delta, direction_xz) / denominator
        if t > 0 and 0 <= u <= 1:
            hits.append(t)
    assert hits, "Oar must cross the gunwale"
    return min(hits)


def add_oar(geometry, start, direction, length):
    direction = Vector(direction).normalized()
    start = Vector(start)
    across = Vector((direction.z, 0, -direction.x)).normalized()
    up = direction.cross(across).normalized()

    def point(t, sideways=0.0, height=0.0):
        return tuple(start + direction * t + across * sideways + up * height)

    # Ten shaft sectors keep adjacent normals 36° apart. The end lips soften
    # the handle; the main shaft has the specified 0.05 m diameter.
    shaft_end = length - 0.40 + 0.06
    previous = None
    for t, radius in ((0.0, 0.020), (0.008, 0.025),
                       (shaft_end - 0.008, 0.025), (shaft_end, 0.020)):
        ring = geometry.ring(point(t, radius * math.cos(math.tau * i / 10),
                                   radius * math.sin(math.tau * i / 10))
                             for i in range(10))
        if previous is None:
            geometry.face(tuple(reversed(ring)))
        else:
            geometry.bridge(previous, ring)
        previous = ring
    geometry.face(previous)

    # A chunky, rounded paddle, exactly 0.40 long and 0.15 wide in its own
    # plane. Six cross-section layers give its 0.025 m thick edges a two-segment
    # bevel, with a 0.003 m radius (12% of the shortest dimension).
    blade = ((0.0, -0.030), (0.060, -0.075), (0.350, -0.075), (0.400, -0.040),
             (0.400, 0.040), (0.350, 0.075), (0.060, 0.075), (0.0, 0.030))
    # inset_polygon expects clockwise points.
    blade = tuple(reversed(blade))
    previous = None
    bevel_mid = 0.003 * (1.0 - math.sqrt(0.5))
    for height, inset in ((-0.0125, 0.003), (-0.0125 + bevel_mid, bevel_mid),
                           (-0.0095, 0.0), (0.0095, 0.0),
                           (0.0125 - bevel_mid, bevel_mid), (0.0125, 0.003)):
        ring = geometry.ring(point(length - 0.40 + t, side, height)
                             for t, side in inset_polygon(blade, inset))
        if previous is None:
            geometry.face(tuple(reversed(ring)))
        else:
            geometry.bridge(previous, ring)
        previous = ring
    geometry.face(previous)


def make_oars(material):
    geometry = Geometry()
    direction = Vector((0.82, 0.18, 0.57)).normalized()
    start_xz = (-0.26, -0.75)
    # Measure from the OUTER edge, not the rim centre, for a full 0.4 m
    # protrusion beyond the gunwale along the oar axis.
    centre_t = rim_crossing(start_xz, (direction.x, direction.z))
    outer_t = rim_crossing(start_xz, (direction.x, direction.z), inset=0.0)
    start = (start_xz[0], 0.625 - direction.y * centre_t, start_xz[1])
    add_oar(geometry, start, direction, outer_t + 0.40)
    a, b = Vector((0.28, 0.505, -0.87)), Vector((-0.14, 0.535, 0.87))
    add_oar(geometry, a, (b - a).normalized(), (b - a).length)
    return geometry.object("Oars", [material])


def read_glb(path):
    """Inspect exported triangles, materials, hierarchy and Godot-space bounds."""
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
    assert document is not None and binary is not None, "Missing GLB chunks"

    def accessor(index):
        a = document["accessors"][index]
        view = document["bufferViews"][a["bufferView"]]
        component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        fmt = "<" + component * width
        stride = view.get("byteStride", struct.calcsize(fmt))
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, start + i * stride) for i in range(a["count"])]

    objects, names, triangles = {}, [], 0

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
            name = node["name"]
            names.append(name)
            points = objects.setdefault(name, [])
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                assert primitive.get("mode", 4) == 4, "Export must contain triangles"
                assert "NORMAL" in primitive["attributes"], "Missing smooth normals"
                points.extend(world @ Vector(p) for p in accessor(primitive["attributes"]["POSITION"]))
                count = document["accessors"][primitive["indices"]]["count"]
                assert count % 3 == 0, "Invalid triangle indices"
                triangles += count // 3
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, Matrix.Identity(4))
    assert sorted(names) == sorted(NAMES), f"Unexpected objects: {names}"
    assert triangles <= 1500, f"Triangle hard limit exceeded: {triangles}"
    hull = objects["Hull"]
    lo = [min(p[i] for p in hull) for i in range(3)]
    hi = [max(p[i] for p in hull) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    assert all(abs(actual - expected) <= expected * 0.10
               for actual, expected in zip(size, (1.1, 0.6, 2.6))), size
    assert abs(lo[1]) < 1e-6, f"Hull bottom must be y=0: {lo[1]}"
    assert abs(lo[0] + hi[0]) < 1e-6 and abs(lo[2] + hi[2]) < 1e-6, "Origin moved"
    assert abs(hi[2] - 1.3) < 1e-5 and abs(lo[2] + 1.3) < 1e-5
    # Inspect the real exported upper shell: the rounded, narrower end must
    # point +Z, while the broad stern faces -Z. This catches an axis reversal.
    front = [abs(p.x) for p in hull if p.y >= 0.51 and 0.75 <= p.z <= 1.20]
    rear = [abs(p.x) for p in hull if p.y >= 0.51 and -1.20 <= p.z <= -0.75]
    assert front and rear and max(front) + 0.02 < max(rear), "Bow must face Godot +Z"
    all_points = [p for points in objects.values() for p in points]
    min_y = min(p.y for p in all_points)
    assert abs(min_y) < 1e-6, f"Part below hull bottom: {min_y}"
    assert not document.get("cameras") and not document.get("textures")
    assert not document.get("images") and not document.get("animations")
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
                      "file_size_bytes": len(data), "triangle_count": triangles,
                      "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
                      "godot_min_y_m": round(min_y, 7),
                      "object_names": names,
                      "material_names": [m["name"] for m in materials]}))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    objects = (make_hull(materials), make_seats(materials["M_wood_dark"]),
               make_oars(materials["M_wood_light"]))
    triangle_count = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        triangle_count += len(obj.data.loop_triangles)
    assert triangle_count <= 1500, f"Triangle hard limit exceeded: {triangle_count}"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj in objects)
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
