class_name Enemy extends CharacterBody3D
# 열거형 상태 머신 기반 적. 슬라임·게는 진입 조건과 대기 행동만 재정의한다. 설계: docs/architecture/enemies-ai.md

enum State { IDLE, PATROL, CHASE, ATTACK, HURT, DEAD }

signal died(enemy: Enemy)
signal state_changed(state: State)

@export var max_hp: int = 30
@export var move_speed: float = 1.5
@export var chase_speed: float = 2.8
@export var attack_range: float = 1.1
@export var attack_damage: float = 8.0
@export var attack_cooldown: float = 1.2
@export var hurt_time: float = 0.25
@export var knockback_speed: float = 3.0
@export var gravity: float = 20.0

var state: State = State.IDLE
var hp: int
var target: Node3D                         # group "player"의 첫 노드

var _nav_ready: bool = false
var _attack_cd: float = 0.0
var _hurt_left: float = 0.0
var _knockback: Vector3 = Vector3.ZERO
var _removed: bool = false
var _flash_mat: StandardMaterial3D
var _flash_tween: Tween

@onready var nav: SmartNavigationAgent = $Nav
@onready var visual: Node3D = $Visual
@onready var _repath: Timer = $RepathTimer

func _ready() -> void:
	hp = max_hp
	target = get_tree().get_first_node_in_group(&"player") as Node3D
	if target != null and target.has_signal(&"player_died"):
		target.connect(&"player_died", _on_player_died)
	nav.avoidance_enabled = true
	nav.radius = 0.5
	nav.neighbor_distance = 5.0
	nav.max_neighbors = 6
	nav.path_desired_distance = 0.5
	nav.target_desired_distance = 0.8
	_repath.wait_time = 0.2
	_repath.timeout.connect(_on_repath)
	_setup_flash()
	_setup_nav.call_deferred()

## 스폰 연출(시각 전용): Visual 스케일 0 → 1, 0.4초. despawn()의 스케일 0 Tween과 대칭.
func spawn_in() -> void:
	visual.scale = Vector3.ZERO
	create_tween().tween_property(visual, "scale", Vector3.ONE, 0.4)

func take_damage(amount: int, from_pos: Vector3) -> void:
	if state == State.DEAD or _removed:
		return
	hp -= amount
	if hp <= 0:
		_die()
		return
	var away := global_position - from_pos
	away.y = 0.0
	_knockback = (away.normalized() if away.length() > 0.001 else Vector3.BACK) * knockback_speed
	_hurt_left = hurt_time
	_flash()
	_set_state(State.HURT)

## 스케일 0 Tween 0.4초 후 queue_free (died는 내지 않음)
func despawn() -> void:
	if _removed:
		return
	_remove_from_world()
	var tw := create_tween()
	tw.tween_property(visual, "scale", Vector3.ZERO, 0.4)
	tw.tween_callback(queue_free)

# ---------------------------------------------------------------- 하위 클래스 재정의

func _should_chase(_dist: float) -> bool:
	return false

func _should_give_up(_dist: float) -> bool:
	return false

## 대기 상태에서 매 물리 프레임 호출 (슬라임: 배회 목표 갱신)
func _idle_update(_delta: float) -> void:
	pass

## PATROL 상태에서 매 물리 프레임 호출 (게)
func _patrol_update(_delta: float) -> void:
	pass

func _visual_update(_delta: float, _moving: bool) -> void:
	pass

func _on_attack() -> void:
	pass

func _on_nav_ready() -> void:
	pass

## 추적을 포기했을 때 돌아가는 상태
func _rest_state() -> State:
	return State.IDLE

# ---------------------------------------------------------------- 상태 머신

func _physics_process(delta: float) -> void:
	if state == State.DEAD or _removed:
		return
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= gravity * delta
	_attack_cd = maxf(_attack_cd - delta, 0.0)

	var dist := _dist_to_target()
	var horizontal := Vector3.ZERO
	match state:
		State.IDLE, State.PATROL:
			if target != null and _should_chase(dist):
				_set_state(State.CHASE)
			else:
				if state == State.IDLE:
					_idle_update(delta)
				else:
					_patrol_update(delta)
				horizontal = _nav_velocity(move_speed, delta)
		State.CHASE:
			if target == null or _should_give_up(dist):
				_set_state(_rest_state())
			elif dist <= attack_range:
				_set_state(State.ATTACK)
			else:
				horizontal = _nav_velocity(chase_speed, delta)
		State.ATTACK:
			if target == null:
				_set_state(_rest_state())
			elif dist > attack_range + 0.3:
				_set_state(State.CHASE)
			else:
				_face_attack(target.global_position - global_position, delta)
				if _attack_cd <= 0.0:
					_attack_cd = attack_cooldown
					target.call(&"take_damage", attack_damage)
					_on_attack()
		State.HURT:
			_hurt_left -= delta
			horizontal = _knockback
			_knockback = _knockback.move_toward(Vector3.ZERO, knockback_speed * 6.0 * delta)
			if _hurt_left <= 0.0:
				_set_state(State.CHASE if target != null and not _should_give_up(dist) else _rest_state())

	velocity.x = horizontal.x
	velocity.z = horizontal.z
	move_and_slide()
	var moving := horizontal.length() > 0.1
	if moving and state != State.HURT:
		_face(horizontal, delta)
	_visual_update(delta, moving)

func _set_state(new_state: State) -> void:
	if state == State.DEAD or state == new_state:
		return
	state = new_state
	if _nav_ready:
		if new_state == State.IDLE:
			nav.target_position = global_position        # 이전 목표 취소
		elif new_state == State.CHASE and target != null:
			nav.move_to(target.global_position)
	state_changed.emit(state)

func _dist_to_target() -> float:
	if target == null:
		return INF
	var d := target.global_position - global_position
	return Vector2(d.x, d.z).length()

func _nav_velocity(speed: float, delta: float) -> Vector3:
	if not _nav_ready:
		return Vector3.ZERO
	nav.max_speed = speed
	return nav.update_movement(delta)

## 공격 중 바라보는 방식. 기본은 이동 방향과 같은 규칙(Visual +Z가 대상 쪽).
func _face_attack(dir: Vector3, delta: float) -> void:
	_face(dir, delta)

func _face(dir: Vector3, delta: float) -> void:
	if Vector2(dir.x, dir.z).length() < 0.001:
		return
	visual.rotation.y = lerp_angle(visual.rotation.y, atan2(dir.x, dir.z), 1.0 - exp(-10.0 * delta))

## 첫 목표 지정은 지연한다: 내비 맵 동기화 후 시작.
func _setup_nav() -> void:
	await get_tree().physics_frame
	if _removed:
		return
	_nav_ready = true
	_repath.start()
	_on_nav_ready()

## 재탐색은 0.2초 간격 타이머에서만.
func _on_repath() -> void:
	if state == State.CHASE and target != null and _nav_ready:
		nav.move_to(target.global_position)

func _on_player_died() -> void:
	target = null
	if state != State.DEAD:
		_set_state(State.IDLE)

func _die() -> void:
	_remove_from_world()
	state = State.DEAD
	died.emit(self)
	state_changed.emit(state)
	var tw := create_tween()
	tw.tween_property(visual, "scale", Vector3.ZERO, 0.4)
	tw.tween_callback(queue_free)

func _remove_from_world() -> void:
	_removed = true
	_repath.stop()
	remove_from_group(&"enemy")
	remove_from_group(&"night_enemy")
	for c in get_children():
		if c is CollisionShape3D:
			(c as CollisionShape3D).set_deferred("disabled", true)

# ---------------------------------------------------------------- 피격 플래시

func _setup_flash() -> void:
	_flash_mat = StandardMaterial3D.new()
	_flash_mat.albedo_color = Color(1, 1, 1, 0)
	_flash_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_flash_mat.roughness = 1.0
	_flash_mat.metallic_specular = 0.0
	for m in visual.find_children("*", "MeshInstance3D", true, false):
		(m as MeshInstance3D).material_overlay = _flash_mat

func _flash() -> void:
	if _flash_tween != null:
		_flash_tween.kill()
	_flash_mat.albedo_color.a = 0.8
	_flash_tween = create_tween()
	_flash_tween.tween_property(_flash_mat, "albedo_color:a", 0.0, 0.1)
