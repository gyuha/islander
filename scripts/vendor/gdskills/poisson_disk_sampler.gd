# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/procedural_generation_poisson_disk_sampling_2d.gd
# Modified for dongval: extends Node → RefCounted + class_name PoissonDiskSampler, static generate_points(…, seed, k, max_points),
#   전체 점 비교(O(n²)) → 배경 격자(셀 r/√2) 이웃 검사, 시작점도 결과에 포함, RNG는 함수 지역(스레드 안전).
class_name PoissonDiskSampler extends RefCounted

@warning_ignore("shadowed_global_identifier")
static func generate_points(width: float, height: float, radius: float, seed: int, k: int = 30, max_points: int = 2000) -> Array[Vector2]:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var cell := radius / sqrt(2.0)
	var cols := int(ceil(width / cell))
	var rows := int(ceil(height / cell))
	var grid := PackedInt32Array()          # 셀 → points 인덱스, -1 = 비어 있음
	grid.resize(cols * rows)
	grid.fill(-1)
	var points: Array[Vector2] = []
	var active: Array[int] = []             # points 인덱스

	var first := Vector2(width / 2.0, height / 2.0)
	points.append(first)
	active.append(0)
	grid[_cell_index(first, cell, cols, rows)] = 0

	while not active.is_empty() and points.size() < max_points:
		var ai := rng.randi() % active.size()
		var center := points[active[ai]]
		var accepted := false

		for i in range(k):
			var angle := rng.randf() * PI * 2.0
			var dir := Vector2(cos(angle), sin(angle))
			var candidate := center + dir * rng.randf_range(radius, 2.0 * radius)

			if _is_valid(candidate, width, height, radius, cell, cols, rows, grid, points):
				points.append(candidate)
				active.append(points.size() - 1)
				grid[_cell_index(candidate, cell, cols, rows)] = points.size() - 1
				accepted = true
				break

		if not accepted:
			active[ai] = active[active.size() - 1]
			active.pop_back()

	return points

static func _cell_index(p: Vector2, cell: float, cols: int, rows: int) -> int:
	var cx := clampi(int(p.x / cell), 0, cols - 1)
	var cy := clampi(int(p.y / cell), 0, rows - 1)
	return cy * cols + cx

static func _is_valid(p: Vector2, w: float, h: float, r: float, cell: float, cols: int, rows: int, grid: PackedInt32Array, points: Array[Vector2]) -> bool:
	if p.x < 0.0 or p.x > w or p.y < 0.0 or p.y > h:
		return false
	var cx := clampi(int(p.x / cell), 0, cols - 1)
	var cy := clampi(int(p.y / cell), 0, rows - 1)
	for y in range(maxi(cy - 2, 0), mini(cy + 3, rows)):
		for x in range(maxi(cx - 2, 0), mini(cx + 3, cols)):
			var idx := grid[y * cols + x]
			if idx >= 0 and p.distance_to(points[idx]) < r:
				return false
	return true
