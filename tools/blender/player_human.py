"""Build the unrigged clay human explorer with Blender 5.2.

Run externally (do not run Blender in the agent sandbox):
    blender -b --factory-startup -P tools/blender/player_human.py

All construction coordinates and the pivot table are WORLD Godot metres:
+Y up, +Z front. Blender (x, y, z) = Godot (x, -z, y).
Rotation and scale alone are applied; joint translations must survive export.
Only player_human.glb is written. No rig, tool, collision, textures or animation.
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
OUTPUT = ROOT / "assets/models/player_human/player_human.glb"
COLORS = {
    "M_skin": "F2C6A0",
    "M_trunk": "8A5A3B",
    "M_cream": "F2E7BB",
    "M_orange": "E79C62",
    "M_ink": "2B2233",
    "M_blush": "F2A0B8",
}
PIVOTS = {
    "PlayerHuman": (0, 0, 0),
    "Body": (0, 0.20, 0),
    "Head": (0, 0.52, 0),
    "ArmL": (0.18, 0.46, 0),
    "ArmR": (-0.18, 0.46, 0),
    "ToolSocket": (-0.18, 0.30, 0.03),
    "LegL": (0.08, 0.20, 0),
    "LegR": (-0.08, 0.20, 0),
}
PARENTS = {
    "PlayerHuman": None,
    "Body": "PlayerHuman",
    "Head": "Body",
    "ArmL": "Body",
    "ArmR": "Body",
    "ToolSocket": "ArmR",
    "LegL": "PlayerHuman",
    "LegR": "PlayerHuman",
}
MESH_NAMES = set(PIVOTS) - {"PlayerHuman", "ToolSocket"}
# Even budgets: a collapse on these closed surfaces removes two triangles.
# Leave 20 triangles below the hard export limit; no runtime budget guessing.
TRIANGLE_BUDGETS = {"Head": 1360, "Body": 900, "ArmL": 180,
                    "ArmR": 180, "LegL": 180, "LegR": 180}
# In Part.add order. Simplify each solid independently so tiny face details
# cannot be sacrificed to reduce the error of a much larger scalp or boot.
SOLID_BUDGETS = {
    # skull, ears, (eye/highlight/cheek) x2, smile, hair
    "Head": (300, 40, 40, 48, 24, 40, 48, 24, 40, 96, 660),
    # shirt, shorts x2, scarf ring/knot/tail, pack/lid, straps x2
    "Body": (180, 80, 80, 130, 40, 80, 100, 70, 70, 70),
    "ArmL": (100, 48, 32), "ArmR": (100, 48, 32),
    "LegL": (80, 100), "LegR": (80, 100),
}
EYEBROW_Y = 0.770
FACE_FRONT_Z = 0.210


def reset_scene():
    # Match player_bunny.py: remove datablocks so rerunning is deterministic.
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
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


def to_godot(p):
    return (p[0], p[2], -p[1])


def smooth_clay(mesh):
    # Pure interpolated surface normals: no weighted/custom or angle splits.
    assert not mesh.has_custom_normals, "Unexpected custom split normals"
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = False
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    for face in bm.faces:
        face.smooth = True
    for edge in bm.edges:
        edge.smooth = True
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


class Part:
    """Accumulate intersecting coloured solids into one named joint mesh."""

    def __init__(self):
        self.vertices = []
        self.faces = []
        self.material_indices = []
        self.solids = []
        self.face_solids = set()
        self.skin_surface = None

    def add(self, vertices, faces, material):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset + i for i in face) for face in faces)
        self.material_indices.extend([list(COLORS).index(material)] * len(faces))
        self.solids.append((offset, len(self.vertices),
                            tuple(min(p[i] for p in vertices) for i in range(3)),
                            tuple(max(p[i] for p in vertices) for i in range(3))))

    def rings(self, profiles, segments, transform, material):
        """Closed solid; profiles are (height, x radius, z radius).

        Poles use one vertex. Nonzero endpoints have flat polygon caps.
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

    def ellipsoid(self, center, size, material, segments=8, steps=4, warp=None):
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
                segments=8):
        cap = min(width / 2, height / 2)
        k = math.sqrt(0.5)
        profiles = [(0, 0, 0),
                    (cap * (1 - k), width * k / 2, depth * k / 2),
                    (cap, width / 2, depth / 2),
                    (height - cap, width / 2, depth / 2),
                    (height - cap * (1 - k), width * k / 2, depth * k / 2),
                    (height, 0, 0)]
        self.rings(profiles, segments,
                   lambda p: (p[0] + center_xz[0], p[1] + bottom,
                              p[2] + center_xz[1]), material)

    def box(self, center, size, material, tilt=0):
        """Actual applied Bevel modifier, with dimensions already in metres."""
        x, y, z = (v / 2 for v in size)
        vertices = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                    (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        mesh = bpy.data.meshes.new("_HumanBevelMesh")
        mesh.from_pydata([to_blender(p) for p in vertices], [], faces)
        mesh.update()
        smooth_clay(mesh)
        obj = bpy.data.objects.new("_HumanBevel", mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bevel = obj.modifiers.new("Clay bevel", "BEVEL")
        bevel.limit_method = "ANGLE"
        bevel.angle_limit = math.radians(30)
        bevel.width = min(size) * 0.125
        # A low-resolution bevel cage is rounded by the part's subdivision.
        bevel.segments = 1
        bpy.ops.object.modifier_apply(modifier=bevel.name)
        # Tilt the scarf tail's geometry only; object rotations stay zero.
        c, s = math.cos(tilt), math.sin(tilt)
        vertices = []
        for vertex in obj.data.vertices:
            px, py, pz = to_godot(vertex.co)
            vertices.append((center[0] + c * px - s * py,
                             center[1] + s * px + c * py, center[2] + pz))
        self.add(vertices, [tuple(p.vertices) for p in obj.data.polygons], material)
        result_mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(result_mesh)

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
        smooth_clay(mesh)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        attach(obj, name, parent)
        # Disconnected solids keep their own dimensions through subdivision
        # shrinkage and simplification. Groups interpolate across modifiers.
        for index, (start, end, _, _) in enumerate(self.solids):
            group = obj.vertex_groups.new(name=f"_ClaySolid{index}")
            group.add(list(range(start, end)), 1.0, "REPLACE")
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        # NEVER apply location: joint origins must be glTF node translations.
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        subdivision = obj.modifiers.new("Clay subdivision", "SUBSURF")
        subdivision.subdivision_type = "CATMULL_CLARK"
        subdivision.levels = subdivision.render_levels = 1
        bpy.ops.object.modifier_apply(modifier=subdivision.name)
        regions = self.limit_triangles(obj, name, materials)
        budget = TRIANGLE_BUDGETS[name]
        for vertices, (_, _, low, high) in zip(regions, self.solids):
            assert vertices, "Simplification removed a clay detail"
            points = [to_godot(v.co) for v in vertices]
            # Local mesh -> world Godot; NEVER move the object/pivot.
            actual_low = [min(p[i] + pivot[i] for p in points) for i in range(3)]
            actual_high = [max(p[i] + pivot[i] for p in points) for i in range(3)]
            for vertex, point in zip(vertices, points):
                world = []
                for i in range(3):
                    span = actual_high[i] - actual_low[i]
                    assert span > 1e-8, "Collapsed clay solid"
                    world.append(low[i] + (point[i] + pivot[i] - actual_low[i])
                                 * (high[i] - low[i]) / span)
                vertex.co = to_blender(tuple(world[i] - pivot[i] for i in range(3)))
        if self.skin_surface is not None:
            # Keep the existing eye/cheek/mouth relief attached to the final
            # smoothed skin rather than the old, coarser construction sphere.
            skin_ids = {v.index for v in regions[0]}
            final_skin = BVHTree.FromPolygons(
                [Vector(tuple(to_godot(v.co)[i] + pivot[i] for i in range(3)))
                 for v in obj.data.vertices],
                [tuple(p.vertices) for p in obj.data.polygons
                 if all(i in skin_ids for i in p.vertices)], all_triangles=False)
            for index in self.face_solids:
                for vertex in regions[index]:
                    p = Vector(tuple(to_godot(vertex.co)[i] + pivot[i] for i in range(3)))
                    origin = Vector((p.x, p.y, 1))
                    direction = Vector((0, 0, -1))
                    old, _, _, _ = self.skin_surface.ray_cast(origin, direction)
                    new, _, _, _ = final_skin.ray_cast(origin, direction)
                    assert old is not None and new is not None, "Facial detail misses final skin"
                    p.z += new.z - old.z
                    vertex.co = to_blender(tuple(p[i] - pivot[i] for i in range(3)))
            # Collapse can interpolate across the curved rim. Keep any such
            # lower front vertices behind the actual final skin, not just an
            # ideal sphere. Head's only trunk solid is the continuous hair cap.
            for vertex in regions[-1]:
                p = Vector(tuple(to_godot(vertex.co)[i] + pivot[i] for i in range(3)))
                p.z = min(p.z, FACE_FRONT_Z - 0.010)
                if p.y <= EYEBROW_Y and abs(p.x) <= 0.185 and p.z > 0:
                    hit, _, _, _ = final_skin.ray_cast(Vector((p.x, p.y, 1)), Vector((0, 0, -1)))
                    if hit is not None:
                        p.z = min(p.z, hit.z - 0.003)
                vertex.co = to_blender(tuple(p[i] - pivot[i] for i in range(3)))
        obj.vertex_groups.clear()
        smooth_clay(obj.data)
        obj.data.calc_loop_triangles()
        assert len(obj.data.loop_triangles) <= budget, f"Part budget exceeded: {name}"
        obj.select_set(False)
        return obj

    def limit_triangles(self, obj, name, materials):
        """Budget the already subdivided solids, then rejoin into this object."""
        budgets = SOLID_BUDGETS[name]
        assert len(budgets) == len(self.solids), f"Solid layout changed: {name}"
        assert sum(budgets) == TRIANGLE_BUDGETS[name], f"Incorrect budget: {name}"
        source = obj.data
        regions = [set() for _ in self.solids]
        for vertex in obj.data.vertices:
            groups = [g for g in vertex.groups if g.weight > 0.5]
            assert len(groups) == 1, "Lost disconnected clay solid"
            regions[groups[0].group].add(vertex.index)
        joined_vertices, joined_faces, indices, ranges = [], [], [], []
        for region, budget in zip(regions, budgets):
            ids = sorted(region)
            remap = {old: new for new, old in enumerate(ids)}
            polygons = [p for p in source.polygons if p.vertices[0] in region]
            assert polygons and all(all(i in region for i in p.vertices) for p in polygons)
            material = polygons[0].material_index
            assert all(p.material_index == material for p in polygons)
            mesh = bpy.data.meshes.new("_HumanClayBudgetMesh")
            mesh.from_pydata([source.vertices[i].co[:] for i in ids], [],
                             [tuple(remap[i] for i in p.vertices) for p in polygons])
            mesh.update()
            temporary = bpy.data.objects.new("_HumanClayBudget", mesh)
            bpy.context.scene.collection.objects.link(temporary)
            bpy.ops.object.select_all(action="DESELECT")
            temporary.select_set(True)
            bpy.context.view_layer.objects.active = temporary
            mesh.calc_loop_triangles()
            count = len(mesh.loop_triangles)
            if count > budget:
                simplify = temporary.modifiers.new("Clay triangle budget", "DECIMATE")
                simplify.decimate_type = "COLLAPSE"
                simplify.ratio = (budget + 0.25) / count
                simplify.use_collapse_triangulate = True
                bpy.ops.object.modifier_apply(modifier=simplify.name)
            mesh = temporary.data
            mesh.calc_loop_triangles()
            assert len(mesh.loop_triangles) <= budget, f"Solid budget exceeded: {name}"
            offset = len(joined_vertices)
            joined_vertices.extend(tuple(v.co) for v in mesh.vertices)
            joined_faces.extend(tuple(offset + i for i in p.vertices) for p in mesh.polygons)
            indices.extend([material] * len(mesh.polygons))
            ranges.append((offset, len(joined_vertices)))
            bpy.data.objects.remove(temporary, do_unlink=True)
            bpy.data.meshes.remove(mesh)
        mesh = bpy.data.meshes.new(name + "ClayMesh")
        mesh.from_pydata(joined_vertices, [], joined_faces)
        mesh.update()
        for material in materials.values():
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, indices):
            polygon.material_index = index
        obj.data = mesh
        bpy.data.meshes.remove(source)
        obj.vertex_groups.clear()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return [[mesh.vertices[i] for i in range(start, end)] for start, end in ranges]


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


def add_strap(part, x):
    """A rounded 30 x 15 mm belt entirely behind the shirt's rear plane."""
    # Even the section's frontmost edge is behind z=-.130, the deepest
    # shirt-back vertex. Subdivision and collapse stay inside this envelope.
    path = [(0.475, -0.165), (0.505, -0.150),
            (0.470, -0.145), (0.300, -0.155)]
    vertices, faces, sides = [], [], 4
    for i, (y, z) in enumerate(path):
        previous, following = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        dy, dz = following[0] - previous[0], following[1] - previous[1]
        length = math.hypot(dy, dz)
        for j in range(sides):
            a = math.tau * j / sides
            # Elliptical section rounds every edge without a thin flat ribbon.
            r = 0.0075 * math.sin(a)
            vertices.append((x + 0.015 * math.cos(a),
                             y - dz / length * r, z + dy / length * r))
    faces.append(tuple(reversed(range(sides))))
    for i in range(len(path) - 1):
        for j in range(sides):
            k = (j + 1) % sides
            faces.append((i * sides + j, i * sides + k,
                          (i + 1) * sides + k, (i + 1) * sides + j))
    faces.append(tuple((len(path) - 1) * sides + j for j in range(sides)))
    assert max(p[2] for p in vertices) < -0.130, "Strap reaches the shirt"
    part.add(vertices, faces, "M_trunk")


def make_body():
    part = Part()
    # Broad belly, narrower shoulders, rounded lower shirt lip.
    shirt = [(0.267, 0.153, 0.114), (0.278, 0.170, 0.130),
             (0.450, 0.157, 0.125),
             (0.495, 0.150, 0.114), (0.520, 0.124, 0.095)]
    part.rings(shirt, 8, lambda p: p, "M_cream")
    # Two separate flared hems make readable shorts rather than a brown skirt.
    for sign in (-1, 1):
        shorts = [(0.140, 0.082, 0.109), (0.147, 0.095, 0.123),
                  (0.166, 0.095, 0.126), (0.278, 0.083, 0.119)]
        part.rings(shorts, 6, lambda p, s=sign: (p[0] + s * 0.085, p[1], p[2]),
                   "M_trunk")

    vertices, faces = [], []
    major, minor = 8, 4
    for i in range(major):
        a = math.tau * i / major
        for j in range(minor):
            b = math.tau * j / minor
            vertices.append(((0.130 + 0.030 * math.cos(b)) * math.cos(a),
                             0.510 + 0.030 * math.sin(b),
                             (0.110 + 0.030 * math.cos(b)) * math.sin(a)))
    for i in range(major):
        for j in range(minor):
            faces.append((i * minor + j, ((i + 1) % major) * minor + j,
                          ((i + 1) % major) * minor + (j + 1) % minor,
                          i * minor + (j + 1) % minor))
    part.add(vertices, faces, "M_orange")
    part.ellipsoid((0, 0.490, 0.150), (0.070, 0.070, 0.070), "M_orange", 4, 3)
    # +15 degrees makes the hanging lower end lean toward character-left (+X).
    # The top is buried in the knot, leaving the visible tail at about .36-.49.
    part.box((0.015, 0.435, 0.150), (0.070, 0.140, 0.030),
             "M_orange", tilt=math.radians(15))

    part.box((0, 0.380, -0.190), (0.240, 0.240, 0.110), "M_trunk")
    # The lid overlaps the body by 10 mm and retains the -0.245 m rear plane.
    part.box((0, 0.525, -0.185), (0.250, 0.070, 0.120), "M_trunk")
    for x in (-0.09, 0.09):
        add_strap(part, x)
    return part


def add_hair(part):
    """One clipped UV sphere, sculpted in place; never separate tuft solids."""
    rings = 10
    # Keep the rear cage coarse, but sample the forehead every 3.75 degrees.
    # The old 22.5-degree spacing skipped the valleys between fringe lobes.
    azimuths = [math.tau * i / 16 for i in range(16)
                if not math.pi / 4 <= math.tau * i / 16 <= 3 * math.pi / 4]
    azimuths += [math.pi / 2 + i * math.pi / 48 for i in range(-12, 13)]
    azimuths.sort()
    segments = len(azimuths)
    center = Vector((0, 0.720, 0.010))
    radii = Vector((0.210 * 1.08, 0.190 * 1.08, 0.200 * 1.08))

    def front_weight(angle):
        t = min(1.0, max(0.0, math.sin(angle) / 0.55))
        return t * t * (3 - 2 * t)

    # UV sphere: two poles and nine latitude rings. Delete the
    # lower vertices/faces at the ear line, rising to the forehead in front.
    vertices = [tuple(center + Vector((0, radii.y, 0)))]
    angles = [0.0]
    for j in range(1, rings):
        theta = math.pi * j / rings
        for angle in azimuths:
            vertices.append((radii.x * math.sin(theta) * math.cos(angle),
                             center.y + radii.y * math.cos(theta),
                             center.z + radii.z * math.sin(theta) * math.sin(angle)))
            angles.append(angle)
    bottom = len(vertices)
    vertices.append(tuple(center - Vector((0, radii.y, 0))))
    angles.append(0.0)
    faces = []
    for i in range(segments):
        following = (i + 1) % segments
        faces.append((0, 1 + following, 1 + i))
        for j in range(rings - 2):
            a, b = 1 + j * segments, 1 + (j + 1) * segments
            faces.append((a + i, a + following, b + following, b + i))
        last = 1 + (rings - 2) * segments
        faces.append((last + i, last + following, bottom))
    keep = {i for i, p in enumerate(vertices)
            if p[1] >= 0.650 + 0.155 * front_weight(angles[i])}
    faces = [face for face in faces if all(i in keep for i in face)]
    used = sorted({i for face in faces for i in face})
    edges = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            edges[edge] = edges.get(edge, 0) + 1
    rim = {i for edge, count in edges.items() if count == 1 for i in edge}

    # Five soft 10-20 mm surface lumps, plus two broad rounded rear flicks.
    lumps = [(Vector(d).normalized(), amount, spread) for d, amount, spread in (
        ((-0.55, 0.83, 0.05), 0.018, 0.22),
        ((0.48, 0.84, 0.10), 0.014, 0.20),
        ((-0.82, 0.40, -0.40), 0.012, 0.20),
        ((0.88, 0.32, -0.35), 0.016, 0.20),
        ((0.05, 0.65, -0.76), 0.015, 0.22),
    )]
    sculpted = []
    for index in used:
        p = Vector(vertices[index])
        angle = angles[index]
        if index in rim:
            front = front_weight(angle)
            # Three separate rounded .060 m lobes, with .030 m dips.
            # Use the projected forehead width, not overlapping angular
            # Gaussians, so the high points remain between the scallops.
            forehead_y = 0.815
            forehead_radius = radii.x * math.sqrt(
                1 - ((forehead_y - center.y) / radii.y) ** 2)
            fringe_x = forehead_radius * math.cos(angle)
            scallop = sum(
                0.015 * (1 + math.cos(math.tau * (fringe_x - c) / 0.060))
                for c in (-0.060, 0, 0.060) if abs(fringe_x - c) < 0.030)
            p.y = 0.650 + 0.165 * front - scallop * front
            radial = math.sqrt(max(0, 1 - ((p.y - center.y) / radii.y) ** 2))
            p.x = radii.x * radial * math.cos(angle)
            p.z = center.z + radii.z * radial * math.sin(angle)
        direction = Vector(tuple((p[i] - center[i]) / radii[i] for i in range(3))).normalized()
        outward = Vector(tuple(direction[i] / radii[i] for i in range(3))).normalized()
        amount = sum(a * math.exp(-(1 - direction.dot(d)) / spread)
                     for d, a, spread in lumps)
        # Keep the rim orderly; lumps are broad surface deformations, not balls.
        p += outward * min(0.020, amount) * (0.2 if index in rim else 1.0)
        for d in (Vector((-0.55, 0.25, -0.80)).normalized(),
                  Vector((0.55, 0.28, -0.80)).normalized()):
            flick = 0.017 * math.exp(-(1 - direction.dot(d)) / 0.055)
            p += Vector((d.x * 0.7, 0.45, d.z)) * flick
        # Front hair stays behind the face's +.210 m plane, above the eyes.
        p.z = min(p.z, FACE_FRONT_Z - 0.010)
        p.x = min(0.224, max(-0.224, p.x))  # Ears retain the +/- .230 envelope.
        if p.z > 0.090 and abs(p.x) < 0.185:
            p.y = max(p.y, EYEBROW_Y + 0.010)
        sculpted.append(p)
    # Preserve the prescribed .950 m crown through the later clay pass.
    low, high = min(p.y for p in sculpted), max(p.y for p in sculpted)
    for p in sculpted:
        p.y = low + (p.y - low) * (0.950 - low) / (high - low)
    remap = {old: new for new, old in enumerate(used)}
    # A latitude cut has short vertical stair steps where its height changes.
    # Both endpoints were moved onto the same rim: weld those pairs before
    # Solidify, so the shell has one clean boundary and no zero faces.
    rim_by_angle, welded = {}, {}
    for old in used:
        new = remap[old]
        if old in rim:
            key = round(angles[old], 12)
            welded[new] = rim_by_angle.setdefault(key, new)
        else:
            welded[new] = new
    clean_faces = []
    for face in faces:
        clean = tuple(dict.fromkeys(welded[remap[i]] for i in face))
        if len(clean) >= 3:
            clean_faces.append(clean)
    retained = sorted({i for face in clean_faces for i in face})
    dense = {old: new for new, old in enumerate(retained)}
    sculpted = [sculpted[i] for i in retained]
    faces = [tuple(dense[i] for i in face) for face in clean_faces]
    mesh = bpy.data.meshes.new("_HumanHairCapMesh")
    mesh.from_pydata([to_blender(p) for p in sculpted], [],
                     faces)
    mesh.update()
    smooth_clay(mesh)
    obj = bpy.data.objects.new("_HumanHairCap", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    shell = obj.modifiers.new("Closed 20 mm clay hair", "SOLIDIFY")
    shell.thickness = 0.020
    shell.offset = -1.0  # Inward thickness cannot enlarge the face/crown bounds.
    shell.use_rim = True
    bpy.ops.object.modifier_apply(modifier=shell.name)
    part.add([to_godot(v.co) for v in obj.data.vertices],
             [tuple(p.vertices) for p in obj.data.polygons], "M_trunk")
    result_mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(result_mesh)


def face_oval(part, surface, x, y, width, height, depth, material,
              segments=10, steps=4, lift=0.005):
    # Conform to the actual polygonal skin surface, avoiding floating decals.
    profiles = [(-1, 0, 0)]
    for j in range(1, steps):
        a = math.pi * j / steps
        profiles.append((-math.cos(a), math.sin(a), math.sin(a)))
    profiles.append((1, 0, 0))

    def conform(p):
        px, py = x + p[0] * width / 2, y + p[1] * height / 2
        return (px, py, surface(px, py) + lift + p[2] * depth / 2)

    part.rings(profiles, segments, conform, material)


def add_smile(part, surface):
    # Seven sections plus rounded endpoint poles, total outside width .040 m.
    points = [(-0.016, 0.640), (-0.012, 0.635), (-0.006, 0.632),
              (0, 0.631), (0.006, 0.632), (0.012, 0.635), (0.016, 0.640)]
    radius, sides = 0.004, 3
    vertices, faces = [], []
    for i, (x, y) in enumerate(points):
        previous, following = points[max(0, i - 1)], points[min(len(points) - 1, i + 1)]
        dx, dy = following[0] - previous[0], following[1] - previous[1]
        length = math.hypot(dx, dy)
        for j in range(sides):
            a = math.tau * j / sides
            px, py = x - dy / length * radius * math.cos(a), y + dx / length * radius * math.cos(a)
            vertices.append((px, py, surface(px, py) + 0.003 + radius * math.sin(a)))
    for i in range(len(points) - 1):
        for j in range(sides):
            k = (j + 1) % sides
            faces.append((i * sides + j, i * sides + k,
                          (i + 1) * sides + k, (i + 1) * sides + j))
    for i, neighbor in ((0, 1), (len(points) - 1, len(points) - 2)):
        dx, dy = points[i][0] - points[neighbor][0], points[i][1] - points[neighbor][1]
        length = math.hypot(dx, dy)
        x, y = points[i][0] + dx / length * radius, points[i][1] + dy / length * radius
        pole = len(vertices)
        vertices.append((x, y, surface(x, y) + 0.003))
        for j in range(sides):
            faces.append((pole, i * sides + j, i * sides + (j + 1) % sides))
    part.add(vertices, faces, "M_ink")


def make_head():
    part = Part()
    part.ellipsoid((0, 0.720, 0.010), (0.420, 0.380, 0.400), "M_skin", 12, 6)
    skin = BVHTree.FromPolygons([Vector(p) for p in part.vertices], part.faces,
                               all_triangles=False)
    part.skin_surface = skin

    def surface(x, y):
        hit, _, _, _ = skin.ray_cast(Vector((x, y, 1)), Vector((0, 0, -1)))
        assert hit is not None, f"Facial element misses skin at {(x, y)}"
        return hit.z

    for sign in (-1, 1):
        # Ear solids belong to this Part, so they export inside Head only.
        part.ellipsoid((sign * 0.203, 0.682, 0.008),
                       (0.054, 0.074, 0.065), "M_skin", 4, 2)
    face_start = len(part.solids)
    for sign in (-1, 1):
        x = sign * 0.075
        face_oval(part, surface, x, 0.700, 0.070, 0.090, 0.010, "M_ink", 6, 2)
        hx, hy = x + sign * 0.013, 0.721
        # A true highlight sphere, partly embedded in the eye's 10 mm relief.
        part.ellipsoid((hx, hy, surface(hx, hy) + 0.011),
                       (0.020, 0.020, 0.020), "M_cream", 4, 2)
        face_oval(part, surface, sign * 0.130, 0.650, 0.090, 0.090, 0.004,
                  "M_blush", 6, 2, lift=0.001)
    add_smile(part, surface)
    part.face_solids = set(range(face_start, len(part.solids)))
    add_hair(part)
    return part


def make_arm(sign):
    part = Part()
    part.capsule((sign * 0.180, 0), 0.250, 0.230, 0.085, 0.085, "M_skin")
    # The .11 m sleeve is inset .01 m, keeping its outer edge at x=+/-.225.
    sleeve = [(0.390, 0.049, 0.049), (0.397, 0.055, 0.055),
              (0.464, 0.048, 0.048), (0.480, 0.038, 0.038)]
    part.rings(sleeve, 4, lambda p: (p[0] + sign * 0.170, p[1], p[2]), "M_cream")
    # Likewise inset the .10 m hand by .005 m; socket stays exactly on its table.
    part.ellipsoid((sign * 0.175, 0.300, 0.030), (0.100, 0.100, 0.100),
                   "M_skin", 4, 2)
    return part


def make_leg(sign):
    part = Part()
    x = sign * 0.080
    # Both limb shafts are eight-sided capsule cages before subdivision.
    part.capsule((x, 0), 0.080, 0.120, 0.100, 0.100, "M_skin")
    # A single rounded boot/cuff profile replaces the beveled box. Its bottom
    # pole stays at y=0 after smoothing; the toe projects toward +Z.
    boot = [(0, 0, 0), (0.018, 0.065, 0.085),
            (0.065, 0.065, 0.085), (0.085, 0.070, 0.065),
            (0.100, 0.062, 0.057), (0.105, 0, 0)]
    part.rings(boot, 8, lambda p: (p[0] + x, p[1], p[2] + 0.025), "M_trunk")
    return part


def read_glb(path):
    """Independently verify GLB bytes and composed WORLD node transforms."""
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
    nodes_by_name, world_by_name, triangles = {}, {}, 0

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
        nodes_by_name[name], world_by_name[name] = node, world
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
    assert set(pivots) == set(PIVOTS), f"Unexpected/missing nodes: {list(pivots)}"
    assert len(document["nodes"]) == len(PIVOTS), "Extra unreachable nodes"
    assert set(mesh_names) == MESH_NAMES, f"Unexpected mesh nodes: {mesh_names}"
    assert len(document["meshes"]) == len(MESH_NAMES), "Unexpected mesh count"
    assert parents == PARENTS, f"Incorrect hierarchy: {parents}"
    assert all("ear" not in n.lower() for n in pivots), "Separate ear object found"
    for name, expected in PIVOTS.items():
        assert all(abs(actual - target) <= 0.01 for actual, target in zip(pivots[name], expected)), (
            f"World pivot mismatch: {name}: {pivots[name]} != {expected}")
        parent_pivot = PIVOTS[PARENTS[name]] if PARENTS[name] else (0, 0, 0)
        expected_local = Vector(tuple(expected[i] - parent_pivot[i] for i in range(3)))
        world = world_by_name[name]
        parent_world = world_by_name[PARENTS[name]] if PARENTS[name] else Matrix.Identity(4)
        local_translation = (parent_world.inverted() @ world).translation
        assert (local_translation - expected_local).length < 1e-6, f"Lost local pivot: {name}"

    low = [min(p[i] for p in positions) for i in range(3)]
    high = [max(p[i] for p in positions) for i in range(3)]
    size = [high[i] - low[i] for i in range(3)]
    assert triangles <= 3000, f"Hard triangle limit exceeded: {triangles}"
    assert abs(low[1]) < 1e-6, f"Ground contact moved: {low[1]}"
    assert abs(high[1] - 0.95) <= 0.01, f"Hair-tip height: {high[1]}"
    assert abs(size[0] - 0.46) <= 0.01, f"Overall width: {size[0]}"
    head = part_positions["Head"]
    assert abs(max(p.x for p in head) - min(p.x for p in head) - 0.46) < 1e-5, "Head width"
    for name in ("ArmL", "ArmR"):
        assert max(abs(p.x) for p in part_positions[name]) <= 0.225001, f"Wide arm: {name}"
    for name in ("LegL", "LegR"):
        assert abs(min(p.y for p in part_positions[name])) < 1e-6, f"Floating boot: {name}"

    assert not document.get("cameras") and not document.get("textures") and not document.get("images")
    assert not document.get("animations") and not document.get("skins")
    assert "KHR_lights_punctual" not in document.get("extensions", {})
    materials = document["materials"]
    assert len(materials) == 6, f"Expected exactly six materials: {len(materials)}"
    assert sorted(m["name"] for m in materials) == sorted(COLORS), "Material names"
    for material in materials:
        pbr = material["pbrMetallicRoughness"]
        assert abs(pbr.get("roughnessFactor", 1) - 0.85) < 1e-6
        assert pbr.get("metallicFactor", 1) == 0
        expected = linear_rgba(COLORS[material["name"]])
        assert all(abs(a - b) < 1e-6 for a, b in zip(pbr["baseColorFactor"], expected))
        assert not any("Texture" in key for key in pbr), "Unexpected texture"

    # Compare exported WORLD +Z eye positions against Head skin only. Exclude
    # the M_ink smile by position; cheek discs never enter this direction test.
    head_mesh = document["meshes"][nodes_by_name["Head"]["mesh"]]
    eyes, skin_points, skin_faces, hair_points = [], [], [], []
    for primitive in head_mesh["primitives"]:
        material = materials[primitive["material"]]["name"]
        points = [world_by_name["Head"] @ Vector(p)
                  for p in accessor(primitive["attributes"]["POSITION"])]
        if material == "M_ink":
            eyes.extend(p for p in points if 0.650 <= p.y <= 0.750 and abs(p.x) > 0.035)
        elif material == "M_skin":
            offset = len(skin_points)
            indices = ([i[0] for i in accessor(primitive["indices"])]
                       if "indices" in primitive else list(range(len(points))))
            skin_faces.extend(tuple(offset + i for i in indices[j:j + 3])
                              for j in range(0, len(indices), 3))
            skin_points.extend(points)
        elif material == "M_trunk":
            hair_points.extend(points)
    assert eyes and any(p.x > 0 for p in eyes) and any(p.x < 0 for p in eyes), "Missing eyes"
    assert skin_points and hair_points, "Missing skin or hair"
    eye_mean_z = sum(p.z for p in eyes) / len(eyes)
    skin_mean_z = sum(p.z for p in skin_points) / len(skin_points)
    assert eye_mean_z - skin_mean_z >= 0.050, "Face must point toward +Z"
    skin_surface = BVHTree.FromPolygons(skin_points, skin_faces, all_triangles=True)
    hair_vertices_front_of_face = 0
    for p in hair_points:
        in_front = p.z > FACE_FRONT_Z + 1e-6
        if p.y <= EYEBROW_Y and abs(p.x) <= 0.185 and p.z > 0:
            hit, _, _, _ = skin_surface.ray_cast(Vector((p.x, p.y, 1)), Vector((0, 0, -1)))
            in_front |= hit is not None and p.z > hit.z + 1e-6
        hair_vertices_front_of_face += int(in_front)
    assert hair_vertices_front_of_face == 0, "Hair covers the visible face"

    print(json.dumps({
        "glb_absolute_path": str(path.resolve()),
        "file_size_bytes": len(data),
        "triangle_count": triangles,
        "eye_mean_z_minus_skin_mean_z_m": round(eye_mean_z - skin_mean_z, 7),
        "hair_vertices_front_of_face": hair_vertices_front_of_face,
        "godot_bbox_size_xyz_m": [round(v, 7) for v in size],
        "godot_min_y_m": round(low[1], 7),
        "godot_max_y_m": round(high[1], 7),
        "object_names": list(pivots),
        "material_names": [m["name"] for m in materials],
        "pivots": {name: [round(v, 7) for v in p] for name, p in pivots.items()},
    }))


def main():
    reset_scene()
    materials = {name: make_material(name, color) for name, color in COLORS.items()}
    objects = {"PlayerHuman": make_empty("PlayerHuman")}
    builders = {
        "Body": make_body,
        "Head": make_head,
        "ArmL": lambda: make_arm(1),
        "ArmR": lambda: make_arm(-1),
        "LegL": lambda: make_leg(1),
        "LegR": lambda: make_leg(-1),
    }
    for name in PIVOTS:
        if name == "PlayerHuman":
            continue
        parent = objects[PARENTS[name]]
        objects[name] = (make_empty(name, parent) if name == "ToolSocket"
                         else builders[name]().finish(name, materials, parent))
    bpy.context.view_layer.update()
    # Static Subdivision-1 counts: Head 3452 (hair shell 2264), Body 1760,
    # arms 448 each, legs 576 each = 7260 before independent simplification.
    # Static post-collapse budgets: Head 1360, Body 900, arms 180 each,
    # legs 180 each = 2980 triangles (closed-solid collapses remove pairs).
    # Recount the applied geometry; never trust the estimate for export.
    triangles = 0
    for obj in objects.values():
        if obj.type == "MESH":
            assert not obj.modifiers, f"Unapplied modifier on {obj.name}"
            assert all(p.use_smooth for p in obj.data.polygons), f"Flat faces on {obj.name}"
            assert not obj.data.has_custom_normals, f"Split normals on {obj.name}"
            obj.data.calc_loop_triangles()
            triangles += len(obj.data.loop_triangles)
    assert triangles <= 3000, f"Construction triangle limit exceeded: {triangles}"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj.name in PIVOTS)
    bpy.context.view_layer.objects.active = objects["PlayerHuman"]
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format="GLB",
                              use_selection=True, export_yup=True, export_apply=True,
                              export_materials="EXPORT", export_normals=True,
                              export_texcoords=False, export_cameras=False,
                              export_lights=False, export_animations=False)
    read_glb(OUTPUT)


if __name__ == "__main__":
    main()
