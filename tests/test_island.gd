extends "res://tests/test_case.gd"

const SEED := 20261028
const RES := 181
const CELL := 0.5
const RADIUS := 28.0

# 레이아웃·격자는 GDScript에서 수백 ms가 걸리므로 한 번만 만들어 재사용한다(지연 초기화). 노드는 캐시하지 않는다.
var _layout: IslandLayout
var _heights: PackedFloat32Array
var _levels: PackedByteArray

func _prepare() -> void:
	if _layout != null:
		return
	_layout = IslandLayout.build(SEED, RADIUS)
	_heights = _layout.sample_heights(RES, CELL)
	_levels = _layout.sample_levels(RES, CELL)

## 노드가 필요한 테스트만 호출. 트리에 넣지 않으며(@onready 미사용 경로만 호출), 테스트 끝에서 free()한다.
func _gen() -> IslandGenerator:
	_prepare()
	var g := IslandGenerator.new()
	g.seed = SEED
	g.resolution = RES
	g.cell_size = CELL
	g.radius = RADIUS
	g.layout = _layout
	g.heights = _heights
	g._levels = _levels
	return g

func _half() -> float:
	return (RES - 1) * CELL * 0.5

func test_same_seed_same_heights() -> void:
	var a := IslandGenerator.compute_heights(SEED, RES, CELL, RADIUS)
	var b := IslandGenerator.compute_heights(SEED, RES, CELL, RADIUS)
	assert_eq(a.size(), RES * RES, "격자 크기")
	assert_true(a == b, "같은 시드는 같은 높이맵")

func test_different_seed_differs() -> void:
	_prepare()
	var b := IslandGenerator.compute_heights(SEED + 1, RES, CELL, RADIUS)
	assert_true(_heights != b, "다른 시드는 다른 높이맵")

func test_edge_below_sea() -> void:
	_prepare()
	var checked := 0
	var worst := -INF
	for j in RES:
		for i in RES:
			if Vector2(i * CELL - _half(), j * CELL - _half()).length() >= 40.0:
				checked += 1
				worst = maxf(worst, _heights[j * RES + i])
	assert_true(checked > 0, "검사 대상 정점 존재")
	assert_true(worst < 0.0, "중심에서 40 m 이상인 정점의 최대 높이 %f < 0" % worst)

func test_center_is_land() -> void:
	_prepare()
	var c := (RES - 1) >> 1
	assert_near(_heights[c * RES + c], 1.20, 0.01, "중심 높이")
	assert_eq(_layout.level_at(0.0, 0.0), 1, "중심 level")

func test_level_distribution() -> void:
	_prepare()
	var counts := [0, 0, 0, 0]
	var land := 0
	for k in _heights.size():
		if _heights[k] > 0.05:
			land += 1
			counts[_levels[k]] += 1
	assert_true(land > 0, "육지 존재")
	for lv in range(1, 4):
		assert_true(counts[lv] > 0, "level %d 존재" % lv)
	for lv in 4:
		assert_true(counts[lv] <= land * 0.5, "level %d가 육지의 50%% 이하 (%d/%d)" % [lv, counts[lv], land])
	var beach_ratio := float(counts[0]) / float(land)
	assert_true(beach_ratio >= 0.20 and beach_ratio <= 0.40, "해변 비율 20~40%% (%f)" % beach_ratio)
	assert_true(counts[2] + counts[3] >= land * 0.2, "level 2+3 ≥ 20%% (%d/%d)" % [counts[2] + counts[3], land])

func test_cliff_heights() -> void:
	_prepare()
	for i in _layout.plateaus.size():
		var lv := _layout.plateaus[i].level
		var h := IslandLayout.LEVEL_HEIGHT[lv] - IslandLayout.LEVEL_HEIGHT[lv - 1]
		assert_true(h >= 0.6 and h <= 1.2, "고원 %d 절벽 높이 %f" % [i, h])

func test_outlines_smooth() -> void:
	_prepare()
	for pi in _layout.plateaus.size():
		var o := _layout.plateaus[pi].outline
		var n := o.size()
		var worst_gap := 0.0
		var worst_turn := 0.0
		for i in n:
			var p0 := o[i]
			var p1 := o[(i + 1) % n]
			var p2 := o[(i + 2) % n]
			worst_gap = maxf(worst_gap, p0.distance_to(p1))
			worst_turn = maxf(worst_turn, absf((p1 - p0).angle_to(p2 - p1)))
		assert_true(worst_gap <= 0.6, "고원 %d 정점 간격 %f ≤ 0.6" % [pi, worst_gap])
		assert_true(rad_to_deg(worst_turn) <= 15.0, "고원 %d 최대 꺾임각 %f° ≤ 15°" % [pi, rad_to_deg(worst_turn)])

func test_plateaus_nested() -> void:
	_prepare()
	var tier2: Array[IslandLayout.Plateau] = []
	for i in _layout.plateaus.size():
		var p := _layout.plateaus[i]
		if p.level >= 2:
			var parent := _layout.plateaus[p.parent]
			var worst := -INF
			for v in p.outline:
				worst = maxf(worst, parent.radial_offset(v.x, v.y))
			assert_true(worst <= -2.95, "고원 %d가 부모 안쪽 ≥ 2.95 m (최악 %f)" % [i, worst])
		if p.level == 2:
			tier2.append(p)
			var nearest := INF
			for v in p.outline:
				nearest = minf(nearest, v.length())
			assert_true(nearest >= 4.0, "원점에서 2단 윤곽 ≥ 4 m (%f)" % nearest)
	for a in tier2.size():
		for b in range(a + 1, tier2.size()):
			var best := INF
			for va in tier2[a].outline:
				for vb in tier2[b].outline:
					best = minf(best, va.distance_to(vb))
			assert_true(best >= 3.0, "2단 %d–%d 윤곽 최소 거리 %f ≥ 3" % [a, b, best])

func test_land_single_component() -> void:
	_prepare()
	var seen := PackedByteArray()
	seen.resize(RES * RES)
	var components := 0
	for start in RES * RES:
		if _heights[start] <= 0.05 or seen[start] == 1:
			continue
		components += 1
		var stack := PackedInt32Array([start])
		seen[start] = 1
		while not stack.is_empty():
			var k := stack[stack.size() - 1]
			stack.resize(stack.size() - 1)
			var x := k % RES
			var y := floori(k / float(RES))
			for nb in [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]:
				if nb[0] < 0 or nb[0] >= RES or nb[1] < 0 or nb[1] >= RES:
					continue
				var nk: int = nb[1] * RES + nb[0]
				if _heights[nk] > 0.05 and seen[nk] == 0:
					seen[nk] = 1
					stack.append(nk)
	assert_eq(components, 1, "육지 연결 성분 수")

func test_ramp_counts_and_slopes() -> void:
	_prepare()
	var per_plateau := {}
	for r in _layout.ramps:
		per_plateau[r.plateau] = int(per_plateau.get(r.plateau, 0)) + 1
		var slope := rad_to_deg(atan((r.h_top - r.h_foot) / IslandLayout.RAMP_LENGTH))
		assert_true(slope <= 25.0, "경사로(고원 %d) 기울기 %f° ≤ 25°" % [r.plateau, slope])
		if _layout.plateaus[r.plateau].level == 1:
			assert_true(r.h_foot >= 0.12, "1단 경사로 h_foot %f ≥ 0.12" % r.h_foot)
	for i in _layout.plateaus.size():
		assert_true(int(per_plateau.get(i, 0)) >= 1, "고원 %d 경사로 ≥ 1" % i)
	assert_true(int(per_plateau.get(0, 0)) >= 3, "본섬 1단 경사로 ≥ 3 (%d)" % int(per_plateau.get(0, 0)))

func test_nav_faces_respect_cliffs() -> void:
	var g := _gen()
	var faces := g._build_nav_faces()
	assert_true(faces.size() >= 3, "내비 면 존재")
	var bad := 0
	for t in range(0, faces.size(), 3):
		var v0 := faces[t]
		var v1 := faces[t + 1]
		var v2 := faces[t + 2]
		var l0 := _layout.level_at(v0.x, v0.z)
		if l0 == _layout.level_at(v1.x, v1.z) and l0 == _layout.level_at(v2.x, v2.z):
			continue
		var c := (v0 + v1 + v2) / 3.0
		var in_mouth := false
		for r in _layout.ramps:
			if r.in_mouth(c.x, c.z):
				in_mouth = true
				break
		if not in_mouth:
			bad += 1
	assert_eq(bad, 0, "level이 다르고 경사로 입구 밖인 내비 삼각형 수")
	g.free()

func test_navmesh_connects_tiers() -> void:
	var g := _gen()
	var faces := g._build_nav_faces()
	var b := {}
	g._place_all(b)
	var source := IslandGenerator.make_nav_source(faces, IslandGenerator.obstacles_from(b))
	var navmesh := IslandGenerator.make_navmesh()
	NavigationServer3D.bake_from_source_geometry_data(navmesh, source)
	var verts := navmesh.get_vertices()
	var polys: Array[PackedInt32Array] = []
	for i in navmesh.get_polygon_count():
		polys.append(navmesh.get_polygon(i))
	assert_true(polys.size() > 0, "베이크된 다각형 존재")
	# 위치(0.01 m 격자) 기준 변 공유 → 인접 그래프
	var edge_owner := {}
	var adj: Array[PackedInt32Array] = []
	adj.resize(polys.size())
	for pi in polys.size():
		var poly := polys[pi]
		for e in poly.size():
			var a := _key(verts[poly[e]])
			var bk := _key(verts[poly[(e + 1) % poly.size()]])
			var ek := (a + "|" + bk) if a < bk else (bk + "|" + a)
			if edge_owner.has(ek):
				var other: int = edge_owner[ek]
				if other != pi:
					adj[pi].append(other)
					adj[other].append(pi)
			else:
				edge_owner[ek] = pi
	var start := _nearest_poly(polys, verts, Vector3(0.0, IslandLayout.LEVEL_HEIGHT[1], 0.0))
	assert_true(start >= 0, "시작 지점 근처 내비 다각형")
	if start < 0:
		g.free()
		return
	var reach := {start: true}
	var queue := [start]
	while not queue.is_empty():
		var cur: int = queue.pop_front()
		for nb in adj[cur]:
			if not reach.has(nb):
				reach[nb] = true
				queue.append(nb)
	for ri in _layout.ramps.size():
		var r := _layout.ramps[ri]
		var up := r.origin - r.dir * 1.5
		var down := r.origin + r.dir * (IslandLayout.RAMP_LENGTH + 1.0)
		for pt in [[up, r.h_top, "위"], [down, _layout.height_at(down.x, down.y), "아래"]]:
			var p: Vector2 = pt[0]
			var idx := _nearest_poly(polys, verts, Vector3(p.x, pt[1], p.y))
			assert_true(idx >= 0, "경사로 %d %s쪽 내비 다각형 존재" % [ri, pt[2]])
			if idx >= 0:
				assert_true(reach.has(idx), "경사로 %d %s쪽이 시작점과 연결" % [ri, pt[2]])
	var isl := _layout.plateaus[1]
	var iidx := _nearest_poly(polys, verts, Vector3(isl.center.x, IslandLayout.LEVEL_HEIGHT[1], isl.center.y))
	assert_true(iidx >= 0 and reach.has(iidx), "작은 섬 1단 중심이 시작점과 연결")
	g.free()

func _key(v: Vector3) -> String:
	return "%d,%d,%d" % [roundi(v.x * 100.0), roundi(v.y * 100.0), roundi(v.z * 100.0)]

## 점에 가장 가까운 다각형(점이 다각형 xz 투영 안이면 |Δy|, 밖이면 가장 가까운 변까지 3D 거리). 2 m 이내가 없으면 -1.
## 베이크 결과의 다각형은 병합되어 길고 넓을 수 있어 무게중심 거리는 대표값이 되지 못한다.
func _nearest_poly(polys: Array[PackedInt32Array], verts: PackedVector3Array, p: Vector3) -> int:
	var best := -1
	var best_d := 2.0
	var pxz := Vector2(p.x, p.z)
	for i in polys.size():
		var poly := polys[i]
		var pts2 := PackedVector2Array()
		var y_sum := 0.0
		var d := INF
		for e in poly.size():
			var a := verts[poly[e]]
			var b := verts[poly[(e + 1) % poly.size()]]
			pts2.append(Vector2(a.x, a.z))
			y_sum += a.y
			var ab := b - a
			var t := clampf((p - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
			d = minf(d, p.distance_to(a + ab * t))
		if Geometry2D.is_point_in_polygon(pxz, pts2):
			d = minf(d, absf(p.y - y_sum / float(poly.size())))
		if d < best_d:
			best_d = d
			best = i
	return best

func test_walls_in_mesh() -> void:
	var g := _gen()
	var arrays := g._build_mesh_arrays()
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var count := 0
	var y_min := INF
	var y_max := -INF
	for i in normals.size():
		if absf(normals[i].y) < 0.3:
			count += 1
			y_min = minf(y_min, verts[i].y)
			y_max = maxf(y_max, verts[i].y)
	assert_true(count >= 1000, "수직 벽 정점 수 %d ≥ 1000" % count)
	assert_true(y_max - y_min >= 0.6, "벽 정점 y 범위 %f ≥ 0.6" % (y_max - y_min))
	g.free()

func test_placement_counts() -> void:
	var g := _gen()
	var b := {}
	g._place_all(b)
	var mins := { "pine": 25, "palm": 6, "rock": 15, "bush": 8, "beach": 8, "grass": 500, "flowers": 120 }
	for k: String in mins:
		assert_true(b[k].size() >= mins[k], "%s 배치 수 %d ≥ %d" % [k, b[k].size(), mins[k]])
	var violators := 0
	for kind in ["pine", "palm", "rock", "bush"]:
		for t: Transform3D in b[kind]:
			if _layout.wall_distance(t.origin.x, t.origin.z) < 1.0 or _layout.in_any_ramp(t.origin.x, t.origin.z, 1.5):
				violators += 1
	assert_eq(violators, 0, "벽·경사로에 걸린 채집물 수")
	g.free()
