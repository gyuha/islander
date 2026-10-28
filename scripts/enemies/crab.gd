class_name Crab extends Enemy
# 해변 순찰, 6 m 안이면 추적. 설계: docs/architecture/enemies-ai.md

@export var aggro_range: float = 6.0
@export var leash_radius: float = 12.0
@export var patrol_wait: float = 1.5

var home: Vector3
var patrol_points: Array[Vector3] = []

var _patrol_idx: int = 0
var _patrol_dir: int = 1
var _idle_left: float = 0.0
var _anim_t: float = 0.0
var _legs_l: Node3D
var _legs_r: Node3D
var _claw_l: Node3D
var _claw_r: Node3D
var _claw_tween: Tween

func _ready() -> void:
	super()
	_legs_l = visual.find_child("LegsL", true, false) as Node3D
	_legs_r = visual.find_child("LegsR", true, false) as Node3D
	_claw_l = visual.find_child("ClawL", true, false) as Node3D
	_claw_r = visual.find_child("ClawR", true, false) as Node3D

## 스포너가 호출: home과 순찰 점(home 포함)
func setup(home_pos: Vector3, points: Array[Vector3]) -> void:
	home = home_pos
	patrol_points = points

func _player_home_dist() -> float:
	if target == null:
		return INF
	var d := target.global_position - home
	return Vector2(d.x, d.z).length()

func _should_chase(dist: float) -> bool:
	return dist <= aggro_range and _player_home_dist() <= leash_radius

func _should_give_up(_dist: float) -> bool:
	return _player_home_dist() > leash_radius

func _rest_state() -> State:
	return State.PATROL if patrol_points.size() > 1 else State.IDLE

func _on_nav_ready() -> void:
	if patrol_points.size() > 1:
		_go_next_patrol()

## 점 사이를 순서대로 왕복한다(0,1,2,1,0,…).
func _go_next_patrol() -> void:
	if _patrol_idx + _patrol_dir < 0 or _patrol_idx + _patrol_dir >= patrol_points.size():
		_patrol_dir = -_patrol_dir
	_patrol_idx += _patrol_dir
	_set_state(State.PATROL)
	nav.move_to(patrol_points[_patrol_idx])

func _patrol_update(_delta: float) -> void:
	if nav.is_navigation_finished():
		_idle_left = patrol_wait
		_set_state(State.IDLE)

func _idle_update(delta: float) -> void:
	if patrol_points.size() > 1 and _nav_ready:
		_idle_left -= delta
		if _idle_left <= 0.0:
			_go_next_patrol()

func _visual_update(delta: float, moving: bool) -> void:
	if moving:
		_anim_t += delta * 12.0
	var swing := sin(_anim_t) * deg_to_rad(15.0) if moving else 0.0
	if _legs_l != null:
		_legs_l.rotation.z = swing
	if _legs_r != null:
		_legs_r.rotation.z = -swing

## 모델이 90° 돌아 있어(옆걸음) 집게가 Visual +X를 향한다. 공격 중에는 +X가 대상을 향하도록 돌린다.
func _face_attack(dir: Vector3, delta: float) -> void:
	if Vector2(dir.x, dir.z).length() < 0.001:
		return
	visual.rotation.y = lerp_angle(visual.rotation.y, atan2(-dir.z, dir.x), 1.0 - exp(-10.0 * delta))

func _on_attack() -> void:
	if _claw_l == null or _claw_r == null:
		return
	if _claw_tween != null:
		_claw_tween.kill()
	_claw_tween = create_tween().set_parallel(true)
	for claw in [_claw_l, _claw_r]:
		_claw_tween.tween_property(claw, "rotation:x", deg_to_rad(-40.0), 0.15)
		_claw_tween.chain().tween_property(claw, "rotation:x", 0.0, 0.15)
