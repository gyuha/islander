class_name EnemySpawner extends Node3D
# 밤에 슬라임, 시작 시 게를 만든다. 설계: docs/architecture/enemies-ai.md

signal enemy_spawned(enemy: Enemy)

@export var slime_scene: PackedScene
@export var crab_scene: PackedScene
@export var slime_interval: float = 15.0
@export var max_slimes: int = 6
@export var spawn_min_dist: float = 14.0
@export var spawn_max_dist: float = 28.0
@export var player_safe_radius: float = 12.0
@export var start_safe_radius: float = 10.0
@export var max_attempts: int = 10
@export var crab_count: int = 3
@export var crab_respawn_sec: float = 120.0
@export var crab_respawn_min_player_dist: float = 15.0

var rng := RandomNumberGenerator.new()               # activate에서 seed = island.seed + 100
var start_point: Vector3
var land_projector: Callable                         # func(p: Vector3) -> Vector3 ; 기본: 내비 최근접점
var last_attempts: int = 0                           # 테스트용: 마지막 find_spawn_point의 시도 횟수

var _island: IslandGenerator
var _player: Node3D
var _slime_timer: Timer
var _slime_count: int = 0                 # 스폰 번호(슬라임 RNG 시드용)

## generated 이후 Main이 호출
func activate(island: IslandGenerator, player: Node3D) -> void:
	_island = island
	_player = player
	start_point = island.spawn_point
	rng.seed = island.seed + 100
	var map := (island.get_node("NavRegion") as NavigationRegion3D).get_navigation_map()
	land_projector = func(p: Vector3) -> Vector3: return NavigationServer3D.map_get_closest_point(map, p)
	_slime_timer = Timer.new()
	_slime_timer.wait_time = slime_interval
	_slime_timer.timeout.connect(_try_spawn_slime)
	add_child(_slime_timer)
	WorldClock.phase_changed.connect(_on_phase_changed)
	_spawn_initial_crabs()
	if WorldClock.is_night:
		_on_phase_changed(true)

## 실패 시 Vector3.INF. 재귀 없이 횟수 제한 반복. 씬 트리·노드 위치에 접근하지 않는다.
func find_spawn_point(player_pos: Vector3) -> Vector3:
	last_attempts = 0
	for i in max_attempts:
		var angle := rng.randf() * TAU
		var dist := rng.randf_range(spawn_min_dist, spawn_max_dist)
		var c := player_pos + Vector3(cos(angle), 0.0, sin(angle)) * dist
		var p: Vector3 = land_projector.call(c) if land_projector.is_valid() else c
		last_attempts = i + 1
		if Vector2(c.x - p.x, c.z - p.z).length() > 1.0:     # 바다 위 후보
			continue
		if p.distance_to(player_pos) < player_safe_radius:
			continue
		if p.distance_to(start_point) < start_safe_radius:
			continue
		return p
	return Vector3.INF

func _enemies_parent() -> Node:
	return get_parent().get_node_or_null("Enemies") if get_parent() != null else self

func _on_phase_changed(is_night: bool) -> void:
	if is_night:
		_slime_timer.start()
		_try_spawn_slime()
	else:
		_slime_timer.stop()
		for e in get_tree().get_nodes_in_group(&"night_enemy"):
			(e as Enemy).despawn()

func _try_spawn_slime() -> void:
	if slime_scene == null or get_tree().get_nodes_in_group(&"night_enemy").size() >= max_slimes:
		return
	var p := find_spawn_point(_player.global_position)
	if p == Vector3.INF:
		return                                           # 이번 틱은 건너뜀
	var slime := slime_scene.instantiate() as Slime
	slime.rng_seed = _island.seed + 1000 + _slime_count
	_slime_count += 1
	_enemies_parent().add_child(slime)
	slime.global_position = p + Vector3(0.0, 0.1, 0.0)
	slime.spawn_in()
	enemy_spawned.emit(slime)

# ---------------------------------------------------------------- 게

func _spawn_initial_crabs() -> void:
	if crab_scene == null or _island.beach_points.is_empty():
		return
	var indices: Array[int] = []
	for i in _island.beach_points.size():
		indices.append(i)
	for n in mini(crab_count, indices.size()):
		var pick := rng.randi() % indices.size()
		_spawn_crab(_island.beach_points[indices[pick]])
		indices.remove_at(pick)

func _spawn_crab(home: Vector3) -> void:
	var crab := crab_scene.instantiate() as Crab
	_enemies_parent().add_child(crab)
	crab.global_position = (land_projector.call(home) as Vector3) + Vector3(0.0, 0.1, 0.0)
	crab.setup(home, _patrol_points_for(home))
	crab.died.connect(_on_crab_died)
	enemy_spawned.emit(crab)

## home과, home에서 4~10 m인 해변 지점 최대 2개
func _patrol_points_for(home: Vector3) -> Array[Vector3]:
	var points: Array[Vector3] = [home]
	for bp in _island.beach_points:
		if points.size() >= 3:
			break
		var d := Vector2(bp.x - home.x, bp.z - home.z).length()
		if d >= 4.0 and d <= 10.0:
			points.append(bp)
	return points

func _on_crab_died(_crab: Enemy) -> void:
	get_tree().create_timer(crab_respawn_sec).timeout.connect(_respawn_crab)

func _respawn_crab() -> void:
	var candidates: Array[Vector3] = []
	for bp in _island.beach_points:
		if Vector2(bp.x - _player.global_position.x, bp.z - _player.global_position.z).length() >= crab_respawn_min_player_dist:
			candidates.append(bp)
	if candidates.is_empty():
		get_tree().create_timer(10.0).timeout.connect(_respawn_crab)
		return
	_spawn_crab(candidates[rng.randi() % candidates.size()])
