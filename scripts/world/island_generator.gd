class_name IslandGenerator extends Node3D
# 섬 지형·배치·내비 생성. 설계: docs/architecture/world-island.md
# 레이아웃·높이 격자·메시 배열·배치 좌표는 WorkerThreadPool 작업에서, 노드·메시·충돌·내비 등록은 메인 스레드에서 한다.

signal generated(spawn_point: Vector3)
signal _nav_done

const SEA_FLOOR := IslandLayout.SEA_FLOOR     # -2.0
const START_CLEAR_RADIUS := 5.0       # 시작 지점 주변 채집물 제외 반경
const PROP_MIN_SPACING := 1.5         # 이미 배치된 채집물과의 최소 거리
const NAV_OBSTACLE_RADIUS := { &"pine": 0.5, &"palm": 0.4, &"rock": 0.7, &"bush": 0.5 }

const COL_EARTH := Color("#C36F46")
const COL_EARTH_BAND := Color("#B4643F")
const COL_EARTH_DARK := Color("#985033")
const COL_SAND := Color("#E4C799")
const COL_GRASS := Color("#5DB85E")
const COL_GRASS_LIGHT := Color("#79C46A")
const COL_LEAF_DARK := Color("#2F8F57")
const FLOWER_COLORS: Array[Color] = [Color("#F6F1E4"), Color("#F2A0B8"), Color("#FDE254")]

@warning_ignore("shadowed_global_identifier")
@export var seed: int = 20261028
@export var radius: float = 28.0              # 본섬 기준 반지름 R0
@export var cell_size: float = 0.5
@export var resolution: int = 181             # 정점 수(한 변) → 90 m
@export var pine_scene: PackedScene
@export var palm_scene: PackedScene
@export var rock_scene: PackedScene
@export var bush_scene: PackedScene
@export var boat_scene: PackedScene
@export var buoy_scene: PackedScene

var heights: PackedFloat32Array               # 생성 후 읽기 전용 (= layout.sample_heights)
var layout: IslandLayout                      # 생성 후 읽기 전용
var _levels: PackedByteArray                  # 내부: layout.sample_levels (내비 면 필터용)
var beach_points: Array[Vector3] = []         # 게 집/순찰 후보
var spawn_point: Vector3
var worker_msec: int = 0                      # 마지막 워커 작업 소요 시간(측정용)

var _task_id: int = -1
var _build: Dictionary = {}                   # 워커 결과 (메인 스레드가 소비)
var _vc: int = 0                              # 메시 조립 중 정점 개수

@onready var _terrain: MeshInstance3D = $Terrain
@onready var _terrain_shape: CollisionShape3D = $Terrain/TerrainBody/CollisionShape3D
@onready var _nav_region: NavigationRegion3D = $NavRegion
@onready var _props: Node3D = $Props
@onready var _grass: MultiMeshInstance3D = $Grass
@onready var _flowers: MultiMeshInstance3D = $Flowers
@onready var _decor: Node3D = $Decor

func _exit_tree() -> void:
	_wait_task()      # 워커가 도는 중에 종료·해제되면 크래시하므로 끝날 때까지 기다린다

## 비동기. 완료 시 generated 시그널.
func generate() -> void:
	_task_id = WorkerThreadPool.add_task(_worker_build, false, "IslandGenerator.build")

## heights 이중선형 보간. 격자 밖은 해저 높이.
func get_height(x: float, z: float) -> float:
	if heights.is_empty():
		return SEA_FLOOR
	var half := (resolution - 1) * cell_size * 0.5
	var fx := (x + half) / cell_size
	var fz := (z + half) / cell_size
	var max_i := float(resolution - 1)
	if fx < 0.0 or fz < 0.0 or fx > max_i or fz > max_i:
		return SEA_FLOOR
	var ix := mini(int(fx), resolution - 2)
	var iz := mini(int(fz), resolution - 2)
	var tx := fx - ix
	var tz := fz - iz
	var h00 := heights[iz * resolution + ix]
	var h10 := heights[iz * resolution + ix + 1]
	var h01 := heights[(iz + 1) * resolution + ix]
	var h11 := heights[(iz + 1) * resolution + ix + 1]
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)

func is_land(x: float, z: float) -> bool:
	return get_height(x, z) > 0.05

## 순수 함수(노드·씬 접근 없음). = IslandLayout.build(seed, radius).sample_heights(resolution, cell_size)
@warning_ignore("shadowed_global_identifier")
static func compute_heights(seed: int, resolution: int, cell_size: float, radius: float) -> PackedFloat32Array:
	return IslandLayout.build(seed, radius).sample_heights(resolution, cell_size)

## 내비 베이크 파라미터 한 곳(테스트도 사용)
static func make_navmesh() -> NavigationMesh:
	var navmesh := NavigationMesh.new()
	navmesh.cell_size = 0.25
	navmesh.cell_height = 0.25
	navmesh.agent_radius = 0.5
	navmesh.agent_height = 1.0
	navmesh.agent_max_climb = 0.5
	navmesh.agent_max_slope = 40.0
	return navmesh

## 배치 변환 → 장애물 목록(씬 인스턴스와 무관). 소나무·야자수·바위·덤불만.
static func obstacles_from(b: Dictionary) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for kind: StringName in NAV_OBSTACLE_RADIUS:
		for t: Transform3D in b.get(String(kind), []):
			out.append({ "pos": t.origin, "radius": NAV_OBSTACLE_RADIUS[kind] })
	return out

## 내비 소스 지오메트리: 면 + 투영 장애물(높이 2 m, carve). 게임과 테스트가 같은 함수를 쓴다.
static func make_nav_source(faces: PackedVector3Array, obstacles: Array[Dictionary]) -> NavigationMeshSourceGeometryData3D:
	var source := NavigationMeshSourceGeometryData3D.new()
	source.add_faces(faces, Transform3D.IDENTITY)
	for o in obstacles:
		var pos: Vector3 = o["pos"]
		var r: float = o["radius"]
		var corners := PackedVector3Array([
			Vector3(pos.x - r, pos.y, pos.z - r), Vector3(pos.x + r, pos.y, pos.z - r),
			Vector3(pos.x + r, pos.y, pos.z + r), Vector3(pos.x - r, pos.y, pos.z + r)])
		source.add_projected_obstruction(corners, pos.y, 2.0, true)
	return source

# ---------------------------------------------------------------- 워커 스레드

func _worker_build() -> void:
	var t0 := Time.get_ticks_msec()
	layout = IslandLayout.build(seed, radius)
	heights = layout.sample_heights(resolution, cell_size)
	_levels = layout.sample_levels(resolution, cell_size)
	var b := {}
	b["mesh_arrays"] = _build_mesh_arrays()
	b["nav_faces"] = _build_nav_faces()
	_place_all(b)
	_build = b
	worker_msec = Time.get_ticks_msec() - t0
	_on_worker_done.call_deferred()

# ---- 메시 조립 (한 SurfaceTool에 세 조각)

func _v(st: SurfaceTool, pos: Vector3, color: Color) -> int:
	st.set_color(color)
	st.add_vertex(pos)
	_vc += 1
	return _vc - 1

func _tri(st: SurfaceTool, a: int, b: int, c: int) -> void:
	st.add_index(a)
	st.add_index(b)
	st.add_index(c)

func _build_mesh_arrays() -> Array:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_vc = 0
	_add_base_grid(st)
	for pi in layout.plateaus.size():
		_add_plateau(st, layout.plateaus[pi], pi)
	for r in layout.ramps:
		_add_ramp(st, r)
	st.generate_normals()
	return st.commit_to_arrays()

## ① 바닥 격자: 모래·해저만. 캡 아래 숨은 삼각형과 평평한 해저 삼각형은 인덱스에서 뺀다.
func _add_base_grid(st: SurfaceTool) -> void:
	var base := layout.sample_base(resolution, cell_size)
	var half := (resolution - 1) * cell_size * 0.5
	var wd := PackedFloat32Array()
	wd.resize(resolution * resolution)
	for j in resolution:
		for i in resolution:
			var k := j * resolution + i
			_v(st, Vector3(i * cell_size - half, base[k], j * cell_size - half), COL_SAND)
			wd[k] = layout.wall_distance(i * cell_size - half, j * cell_size - half) if _levels[k] >= 1 else INF
	for j in resolution - 1:
		for i in resolution - 1:
			var a := j * resolution + i
			var b := a + 1
			var c := a + resolution
			var d := c + 1
			for tri in [[a, b, c], [b, d, c]]:
				if _hidden_tri(tri, base, wd):
					continue
				_tri(st, tri[0], tri[1], tri[2])      # 위에서 볼 때 시계 방향 = 앞면

func _hidden_tri(tri: Array, base: PackedFloat32Array, wd: PackedFloat32Array) -> bool:
	var under_cap := true
	var flat_floor := true
	for k: int in tri:
		if _levels[k] < 1 or wd[k] < 0.6:
			under_cap = false
		if base[k] > SEA_FLOOR + 0.01:
			flat_floor = false
	return under_cap or flat_floor

## ② 고원 프리즘: 캡(팬) + 립 + 수직 벽(지층 띠) + 발치
func _add_plateau(st: SurfaceTool, p: IslandLayout.Plateau, plateau_index: int) -> void:
	var n := p.outline.size()
	var top := IslandLayout.LEVEL_HEIGHT[p.level]
	var ground := IslandLayout.LEVEL_HEIGHT[p.level - 1]
	var cap_col := COL_GRASS if p.level == 1 else COL_GRASS_LIGHT
	var k := maxi(2, roundi((top - ground - 0.34) / 0.16))
	# 링 정의: [d, dy, 색, 앞 링과 이음 여부]
	var rings: Array[Array] = [
		[-0.20, 0.0, cap_col, false], [-0.10, -0.03, cap_col, true], [-0.02, -0.09, cap_col, true],
		[0.05, -0.17, cap_col, true], [0.03, -0.24, COL_LEAF_DARK, true], [0.03, -0.24, COL_EARTH, false],
	]
	var wall_bottom := ground - top + 0.10
	for j in range(1, k + 1):
		rings.append([0.04 * sin(PI * float(j) / float(k + 1)), lerpf(-0.24, wall_bottom, float(j) / float(k + 1)),
			COL_EARTH_BAND if j % 2 == 1 else COL_EARTH, true])
	rings.append([0.10, ground - top + 0.03, COL_EARTH_DARK, true])
	rings.append([0.14, ground - top - 0.25, COL_EARTH_DARK, true])
	var ring_idx: Array[PackedInt32Array] = []
	for r in rings:
		var idx := PackedInt32Array()
		idx.resize(n)
		for i in n:
			var o := p.outline[i]
			var nr := p.normals[i]
			idx[i] = _v(st, Vector3(o.x + nr.x * float(r[0]), top + float(r[1]), o.y + nr.y * float(r[0])), r[2])
		ring_idx.append(idx)
	# 캡 팬
	var center := _v(st, Vector3(p.center.x, top, p.center.y), cap_col)
	for i in n:
		_tri(st, center, ring_idx[0][i], ring_idx[0][(i + 1) % n])
	# 경사로 입구 구간(길 폭 + 여유)은 립·벽 띠를 만들지 않는다. 경사로 둔덕이 그 자리를 대신한다.
	var in_mouth := PackedByteArray()
	in_mouth.resize(n)
	for ramp in layout.ramps:
		if ramp.plateau != plateau_index:
			continue
		for i in n:
			var st_local := ramp.local(p.outline[i].x, p.outline[i].y)
			if absf(st_local.x) <= 1.0 and absf(st_local.y) <= IslandLayout.RAMP_WIDTH * 0.5 + 0.1:
				in_mouth[i] = 1
	# 링 사이 띠: 바깥에서 볼 때 시계 방향 = (A_i, B_i, A_i+1), (A_i+1, B_i, B_i+1)
	for r in range(1, rings.size()):
		if not bool(rings[r][3]):
			continue
		var upper := ring_idx[r - 1]
		var lower := ring_idx[r]
		for i in n:
			var i2 := (i + 1) % n
			if in_mouth[i] == 1 or in_mouth[i2] == 1:
				continue
			_tri(st, upper[i], lower[i], upper[i2])
			_tri(st, upper[i2], lower[i], lower[i2])

## ③ 경사로 둔덕: 로컬 격자(0.15 m). 지면보다 낮은 부분은 5 cm 아래로 묻는다.
## 색: 길과 양옆 비탈 모두 위 단 캡 색에서 아래 단 지면 색으로 s를 따라 풀어진다(풀 길). 흙색은 절벽 벽 바로 옆(s ≈ 0~1.2 m)의
## 비탈에만 섞는다. 비탈 바깥 0.8 m는 아래 지면 색으로 되돌리고 높이도 5 cm 더 묻어 지면과 만나는 들쭉날쭉한 교선을 감춘다.
func _add_ramp(st: SurfaceTool, r: IslandLayout.Ramp) -> void:
	var step := 0.15
	var ext := r.half_extent()
	var ns := int(ceil((IslandLayout.RAMP_LENGTH + 1.0) / step)) + 1
	var nt := int(ceil(2.0 * ext / step)) + 1
	var tang := Vector2(-r.dir.y, r.dir.x)
	var half_w := IslandLayout.RAMP_WIDTH * 0.5
	var level := layout.plateaus[r.plateau].level
	var top_col := COL_GRASS if level == 1 else COL_GRASS_LIGHT
	var foot_col := COL_SAND if level == 1 else (COL_GRASS if level == 2 else COL_GRASS_LIGHT)
	var first := _vc
	for si in ns:
		var s := minf(-1.0 + si * step, IslandLayout.RAMP_LENGTH)
		var path_col := top_col.lerp(foot_col, smoothstep(0.0, IslandLayout.RAMP_LENGTH, s))
		for ti in nt:
			var t := minf(-ext + ti * step, ext)
			var pt := r.origin + r.dir * s + tang * t
			var at := absf(t)
			var skirt := smoothstep(ext - 0.6, ext, at)                    # 바깥 가장자리 0.6 m
			var y := maxf(r.height_at(pt.x, pt.y), layout.ground_height(pt.x, pt.y) - 0.05) - 0.05 * skirt
			var earth_w := smoothstep(half_w, half_w + 0.5, at) * (1.0 - smoothstep(0.0, 1.2, s))
			var col := path_col.lerp(COL_EARTH, earth_w)
			col = col.lerp(foot_col if s > 0.0 else top_col, smoothstep(ext - 0.8, ext, at))
			_v(st, Vector3(pt.x, y, pt.y), col)
	for si in ns - 1:
		for ti in nt - 1:
			var a := first + si * nt + ti
			var b := a + nt          # s + 1
			var c := a + 1           # t + 1   (s→x, t→z와 같은 방향이라 격자와 같은 감김)
			var d := b + 1
			_tri(st, a, b, c)
			_tri(st, b, d, c)

## 세 정점이 모두 해수면 위(h > 0.05)이고, level이 모두 같거나 무게중심이 경사로 입구 띠 안인 삼각형만.
func _build_nav_faces() -> PackedVector3Array:
	var half := (resolution - 1) * cell_size * 0.5
	var faces := PackedVector3Array()
	for j in resolution - 1:
		for i in resolution - 1:
			var a := Vector2i(i, j)
			var b := Vector2i(i + 1, j)
			var c := Vector2i(i, j + 1)
			var d := Vector2i(i + 1, j + 1)
			for tri: Array in [[a, b, c], [b, d, c]]:
				var ok := true
				var lv0 := -1
				var same_level := true
				var cx := 0.0
				var cz := 0.0
				for v: Vector2i in tri:
					var k := v.y * resolution + v.x
					if heights[k] <= 0.05:
						ok = false
						break
					if lv0 < 0:
						lv0 = _levels[k]
					elif _levels[k] != lv0:
						same_level = false
					cx += v.x * cell_size - half
					cz += v.y * cell_size - half
				if not ok:
					continue
				if not same_level:
					cx /= 3.0
					cz /= 3.0
					var in_mouth := false
					for r in layout.ramps:
						if r.in_mouth(cx, cz):
							in_mouth = true
							break
					if not in_mouth:
						continue
				for v: Vector2i in tri:
					faces.append(Vector3(v.x * cell_size - half, heights[v.y * resolution + v.x], v.y * cell_size - half))
	return faces

func _normal_y(x: float, z: float) -> float:
	var e := cell_size
	var dx := (get_height(x + e, z) - get_height(x - e, z)) / (2.0 * e)
	var dz := (get_height(x, z + e) - get_height(x, z - e)) / (2.0 * e)
	return 1.0 / sqrt(1.0 + dx * dx + dz * dz)

func _place_all(b: Dictionary) -> void:
	var placed: Array[Vector2] = []       # 배치된 채집물 xz (간격 검사용)
	# 인자: 반경, 시드 오프셋, 최대, 조건, 채집물 여부, placed, 벽 거리 ≥, 경사로 제외 여유, max_points
	b["pine"] = _scatter(4.5, 1, 30, func(h: float, ny: float) -> bool: return h >= 0.8 and ny >= 0.92, true, placed, 1.0, 1.5)
	b["palm"] = _scatter(5.0, 2, 10, func(h: float, _ny: float) -> bool: return h >= 0.15 and h <= 0.5, true, placed, 1.0, 1.5)
	b["rock"] = _scatter(6.0, 3, 20, func(h: float, _ny: float) -> bool: return h >= 0.2, true, placed, 1.0, 1.5)
	b["bush"] = _scatter(7.0, 4, 12, func(h: float, _ny: float) -> bool: return h >= 0.8, true, placed, 1.0, 1.5)
	var beach: Array[Vector3] = []
	for t in _scatter(6.0, 5, 12, func(h: float, _ny: float) -> bool: return h >= 0.1 and h <= 0.5, false, placed, 0.8, 0.0):
		beach.append(t.origin)
	b["beach"] = beach
	var grass := _scatter(1.2, 6, 600, func(h: float, ny: float) -> bool: return h >= 0.5 and ny >= 0.9, false, placed, 0.3, 0.0, 8000)
	b["grass"] = grass
	b["grass_colors"] = _pick_colors(grass.size(), [COL_GRASS, COL_GRASS_LIGHT], seed + 106)
	var flowers := _scatter(2.5, 7, 150, func(h: float, _ny: float) -> bool: return h >= 0.5, false, placed, 0.3, 0.0)
	b["flowers"] = flowers
	b["flower_colors"] = _pick_colors(flowers.size(), FLOWER_COLORS, seed + 107)

## Poisson 점 중 조건을 만족하는 것을 순서대로 최대 max_count개 변환으로 돌려준다.
## avoid_props면 시작 지점 반경·기존 채집물 간격을 검사하고 통과한 점을 placed에 추가한다.
## 모든 종류가 벽 거리(wall_min)와 경사로 발자국(ramp_margin) 제외를 적용한다.
func _scatter(r: float, seed_offset: int, max_count: int, accept: Callable, avoid_props: bool, placed: Array[Vector2], wall_min: float, ramp_margin: float, max_points: int = 2000) -> Array[Transform3D]:
	var size := (resolution - 1) * cell_size
	var half := size * 0.5
	var points := PoissonDiskSampler.generate_points(size, size, r, seed + seed_offset, 30, max_points)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed + seed_offset
	var out: Array[Transform3D] = []
	for p in points:
		if out.size() >= max_count:
			break
		var x := p.x - half
		var z := p.y - half
		var h := get_height(x, z)
		if not accept.call(h, _normal_y(x, z)):
			continue
		if layout.wall_distance(x, z) < wall_min or layout.in_any_ramp(x, z, ramp_margin):
			continue
		var xz := Vector2(x, z)
		if avoid_props:
			if xz.length() < START_CLEAR_RADIUS:
				continue
			var too_close := false
			for q in placed:
				if xz.distance_to(q) < PROP_MIN_SPACING:
					too_close = true
					break
			if too_close:
				continue
			placed.append(xz)
		var s := rng.randf_range(0.9, 1.15)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s, s))
		out.append(Transform3D(basis, Vector3(x, h, z)))
	return out

static func _pick_colors(count: int, palette: Array[Color], rng_seed: int) -> PackedColorArray:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var out := PackedColorArray()
	for i in count:
		out.append(palette[rng.randi() % palette.size()])
	return out

# ---------------------------------------------------------------- 메인 스레드

func _wait_task() -> void:
	if _task_id != -1:
		WorkerThreadPool.wait_for_task_completion(_task_id)
		_task_id = -1

func _on_worker_done() -> void:
	_wait_task()
	var b := _build
	_build = {}
	spawn_point = Vector3(0.0, get_height(0.0, 0.0) + 0.5, 0.0)
	beach_points = b["beach"]

	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, b["mesh_arrays"])
	_terrain.mesh = mesh
	_terrain_shape.shape = mesh.create_trimesh_shape()

	_spawn_props(b["pine"], pine_scene, &"pine")
	_spawn_props(b["palm"], palm_scene, &"palm")
	_spawn_props(b["rock"], rock_scene, &"rock")
	_spawn_props(b["bush"], bush_scene, &"bush")
	_setup_multimesh(_grass, _build_grass_mesh(), b["grass"], b["grass_colors"], 0.0)
	var flower_mesh := SphereMesh.new()
	flower_mesh.radius = 0.07
	flower_mesh.height = 0.14
	flower_mesh.radial_segments = 8
	flower_mesh.rings = 4
	_setup_multimesh(_flowers, flower_mesh, b["flowers"], b["flower_colors"], 0.07)
	_spawn_decor()

	await _bake_navigation(b["nav_faces"], obstacles_from(b))
	# 내비 맵이 새 navmesh를 반영할 때까지 물리 프레임을 기다린다(동기화 전 map_get_closest_point는 (0,0,0)을 돌려준다). 최대 10프레임.
	var map := _nav_region.get_navigation_map()
	for i in 10:
		await get_tree().physics_frame
		var closest := NavigationServer3D.map_get_closest_point(map, spawn_point)
		if not closest.is_zero_approx() and closest.distance_to(spawn_point) < 3.0:
			break
	generated.emit(spawn_point)

func _spawn_props(transforms: Array[Transform3D], scene: PackedScene, kind: StringName) -> void:
	if scene == null:
		push_warning("IslandGenerator: %s 씬이 지정되지 않아 건너뜀" % kind)
		return
	for t in transforms:
		var node := scene.instantiate() as Node3D
		_props.add_child(node, true)
		node.transform = t

func _setup_multimesh(target: MultiMeshInstance3D, mesh: Mesh, transforms: Array[Transform3D], colors: PackedColorArray, y_offset: float) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = transforms.size()
	for i in transforms.size():
		var t := transforms[i]
		t.origin.y += y_offset
		mm.set_instance_transform(i, t)
		mm.set_instance_color(i, colors[i])
	target.multimesh = mm
	target.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF

## 높이 0.25 m 원뿔 3개를 합친 풀 메시.
func _build_grass_mesh() -> ArrayMesh:
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.05
	cone.height = 0.25
	cone.radial_segments = 5
	cone.rings = 1
	cone.cap_top = false
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var blades := [
		[Vector3(-0.05, 0.125, 0.0), Vector3.BACK, deg_to_rad(12.0)],
		[Vector3(0.05, 0.125, 0.0), Vector3.BACK, deg_to_rad(-12.0)],
		[Vector3(0.0, 0.125, 0.04), Vector3.RIGHT, deg_to_rad(10.0)],
	]
	for blade in blades:
		st.append_from(cone, 0, Transform3D(Basis(blade[1], blade[2]), blade[0]))
	return st.commit()

func _spawn_decor() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed + 8
	# 보트: 원점→점 방향으로 3 m 바깥이 물(h < −0.3)인 첫 해변 점. 없으면 생략.
	if boat_scene != null:
		for p in beach_points:
			var radial := Vector3(p.x, 0.0, p.z)
			var outward := radial.normalized()
			var spot := radial + outward * 3.0
			if get_height(spot.x, spot.z) >= -0.3:
				continue
			var boat := boat_scene.instantiate() as Node3D
			_decor.add_child(boat, true)
			boat.position = spot + Vector3(0.0, -0.15, 0.0)
			boat.rotation.y = atan2(-outward.x, -outward.z)      # 뱃머리(+Z)가 섬을 향함
			boat.rotation.z = deg_to_rad(-3.0)
			var tw := boat.create_tween().set_loops()
			tw.tween_property(boat, "rotation:z", deg_to_rad(3.0), 1.5).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
			tw.tween_property(boat, "rotation:z", deg_to_rad(-3.0), 1.5).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
			break
	if buoy_scene != null:
		var base_angle := rng.randf() * TAU
		for i in 3:
			var angle := base_angle + i * TAU / 3.0
			var buoy := buoy_scene.instantiate() as Node3D
			_decor.add_child(buoy, true)
			var base_y := -0.08
			buoy.position = Vector3(cos(angle), 0.0, sin(angle)) * rng.randf_range(43.0, 46.0) + Vector3(0.0, base_y - 0.15, 0.0)
			var tw := buoy.create_tween().set_loops()
			tw.tween_property(buoy, "position:y", base_y + 0.15, 1.25).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
			tw.tween_property(buoy, "position:y", base_y - 0.15, 1.25).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)

func _bake_navigation(faces: PackedVector3Array, obstacles: Array[Dictionary]) -> void:
	var navmesh := make_navmesh()
	NavigationServer3D.bake_from_source_geometry_data_async(navmesh, make_nav_source(faces, obstacles), _on_nav_baked.bind(navmesh))
	await _nav_done

func _on_nav_baked(navmesh: NavigationMesh) -> void:
	_nav_region.navigation_mesh = navmesh
	_nav_done.emit()
