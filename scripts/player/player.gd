class_name Player extends CharacterBody3D
# 설계: docs/architecture/player-vitals-interaction.md

signal equipped_changed(item: ItemData)          # null = 맨손
signal focus_changed(prompt: String)             # 빈 문자열 = 대상 없음, 바뀔 때만
signal item_received(item: ItemData, amount: int)
signal inventory_full
signal player_died
signal notice(text: String)                       # HUD 토스트용 짧은 안내

@export var walk_speed: float = 4.5
@export var sprint_speed: float = 7.0
@export var acceleration: float = 30.0
@export var gravity: float = 20.0
@export var hand_damage: int = 4
@export var hand_reach: float = 1.5
@export var attack_cooldown: float = 0.5
@export var attack_hit_delay: float = 0.15
@export var invuln_time: float = 0.5
@export var turn_speed: float = 12.0             # 이동 방향 회전 보간 계수
@export var face_lock_time: float = 0.3          # 공격·상호작용 후 조준 방향 유지 시간
@export var island_path: NodePath                # 물 경계 확인용 IslandGenerator
@export var camera_rig_path: NodePath            # 이동 기준 yaw, 조준 방향

var inventory: InventoryData
var equipped: ItemData = null

var _input_enabled: bool = true
var _dead: bool = false
var _attack_cd: float = 0.0
var _hit_pending: float = -1.0
var _invuln: float = 0.0
var _face_lock: float = 0.0
var _prompt: String = ""
var _anim_t: float = 0.0
var _anim_amp: float = 0.0
var _swing_tween: Tween
var _island: IslandGenerator
var _camera_rig: CameraRig
var _body: Node3D
var _body_base_y: float = 0.0
var _arm_l: Node3D
var _arm_r: Node3D
var _leg_l: Node3D
var _leg_r: Node3D
var _tool_socket: Node3D

@onready var vitals: Vitals = $Vitals
@onready var crafting: CraftingProcessor = $CraftingProcessor
@onready var _visual: Node3D = $Visual
@onready var _hit_cast: ShapeCast3D = $HitCast

func _ready() -> void:
	inventory = InventoryData.create(20)
	inventory.inventory_updated.connect(_on_inventory_updated)
	crafting.configure(inventory, ItemDB.recipes, ItemDB.get_item)
	_island = get_node_or_null(island_path) as IslandGenerator
	_camera_rig = get_node_or_null(camera_rig_path) as CameraRig
	vitals.died.connect(_on_vitals_died)
	# 파츠는 경로가 아니라 이름으로 찾는다(glb 임포트 시 계층 깊이·루트 이름이 달라질 수 있다).
	_body = _visual.find_child("Body", true, false) as Node3D
	_arm_l = _visual.find_child("ArmL", true, false) as Node3D
	_arm_r = _visual.find_child("ArmR", true, false) as Node3D
	_leg_l = _visual.find_child("LegL", true, false) as Node3D
	_leg_r = _visual.find_child("LegR", true, false) as Node3D
	_tool_socket = _visual.find_child("ToolSocket", true, false) as Node3D
	if _body != null:
		_body_base_y = _body.position.y

# ---------------------------------------------------------------- 공개 API

## 남은 수량 반환, 0 초과면 inventory_full
func receive_item(item_id: StringName, amount: int) -> int:
	var item := ItemDB.get_item(item_id)
	if item == null:
		return amount
	var left := inventory.add_item(item, amount)
	if left > 0:
		inventory_full.emit()
	if amount - left > 0:
		item_received.emit(item, amount - left)
	return left

## 무적 중이면 무시
func take_damage(amount: float) -> void:
	if _dead or _invuln > 0.0:
		return
	_invuln = invuln_time
	vitals.take_damage(amount)

## 도구 = 장착 토글, 음식 = 1개 섭취
func use_slot(index: int) -> void:
	if _dead:
		return
	var slot := inventory.get_slot(index)
	if slot == null or slot.is_empty():
		return
	var item := slot.item
	if item.is_tool():
		_set_equipped(null if equipped != null and equipped.id == item.id else item)
	elif item.is_food():
		if vitals.hunger >= vitals.max_hunger - 1.0 and float(item.consumables.get("health", 0.0)) <= 0.0:
			notice.emit("배가 불러요")                     # 배고픔이 이미 가득이면 먹지 않는다
			return
		vitals.eat(item.consumables)
		inventory.remove_at(index, 1)

func set_input_enabled(enabled: bool) -> void:
	_input_enabled = enabled

## Visual yaw를 dir 방향으로 즉시 설정 (조준 정렬, 스폰 시 Main이 카메라 정면으로 호출)
func face_direction(dir: Vector3) -> void:
	if Vector2(dir.x, dir.z).length() < 0.001:
		return
	_visual.rotation.y = atan2(dir.x, dir.z)

# ---------------------------------------------------------------- 루프

func _physics_process(delta: float) -> void:
	_attack_cd = maxf(_attack_cd - delta, 0.0)
	_invuln = maxf(_invuln - delta, 0.0)
	_face_lock = maxf(_face_lock - delta, 0.0)
	if _hit_pending >= 0.0:
		_hit_pending -= delta
		if _hit_pending < 0.0:
			_resolve_attack()

	var input := Vector2.ZERO
	if _input_enabled and not _dead:
		input = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var yaw := _camera_rig.get_yaw() if _camera_rig != null else 0.0
	var dir := Basis(Vector3.UP, yaw) * Vector3(input.x, 0.0, input.y)
	var moving := dir.length() > 0.01
	var sprinting := moving and Input.is_action_pressed("sprint")
	var speed := sprint_speed if sprinting else walk_speed

	vitals.activity = Vitals.Activity.IDLE
	if moving:
		vitals.activity = Vitals.Activity.SPRINT if sprinting else Vitals.Activity.WALK

	var target_vel := dir * speed if moving else Vector3.ZERO
	velocity.x = move_toward(velocity.x, target_vel.x, acceleration * delta)
	velocity.z = move_toward(velocity.z, target_vel.z, acceleration * delta)
	if moving and _island != null:
		var ahead := global_position + dir * speed * delta
		if _island.get_height(ahead.x, ahead.z) < -0.3:      # 물 경계: 수평 속도 0
			velocity.x = 0.0
			velocity.z = 0.0
	if is_on_floor():
		velocity.y = 0.0
	else:
		velocity.y -= gravity * delta
	move_and_slide()

	if moving and _face_lock <= 0.0:
		_visual.rotation.y = lerp_angle(_visual.rotation.y, atan2(dir.x, dir.z), 1.0 - exp(-turn_speed * delta))

	_update_focus()
	_animate_walk(delta, moving)

func _unhandled_input(event: InputEvent) -> void:
	if not _input_enabled or _dead:
		return
	if event.is_action_pressed("attack"):
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED or _attack_cd > 0.0:
			return
		_aim()
		_attack_cd = attack_cooldown
		_hit_pending = attack_hit_delay
		_play_swing()
	elif event.is_action_pressed("interact"):
		_aim()
		var target := _first_key_target(_sweep())
		if target != null:
			target.interact(self)

# ---------------------------------------------------------------- 조준·판정

func _aim() -> void:
	if _camera_rig != null:
		face_direction(_camera_rig.get_forward())
	_face_lock = face_lock_time

func _current_reach() -> float:
	return equipped.reach if equipped != null and equipped.reach > 0.0 else hand_reach

func _current_damage() -> int:
	return equipped.damage if equipped != null and equipped.damage > 0 else hand_damage

## HitCast를 조준 방향·현재 사거리로 맞추고 즉시 갱신. 충돌체를 가까운 순으로 돌려준다.
func _sweep() -> Array[Node3D]:
	var forward := _camera_rig.get_forward() if _camera_rig != null else Vector3.FORWARD
	_hit_cast.target_position = forward * maxf(_current_reach() - 0.5, 0.0)
	_hit_cast.force_shapecast_update()
	var hits: Array[Node3D] = []
	for i in _hit_cast.get_collision_count():
		var c := _hit_cast.get_collider(i) as Node3D
		if c != null and not hits.has(c):
			hits.append(c)
	hits.sort_custom(func(a: Node3D, b: Node3D) -> bool:
		return a.global_position.distance_squared_to(global_position) < b.global_position.distance_squared_to(global_position))
	return hits

## E로 쓸 수 있는 가장 가까운 대상(타격형 나무·바위는 제외)
func _first_key_target(hits: Array[Node3D]) -> Interactable:
	for c in hits:
		if c is Interactable and (c as Interactable).usable_with_key():
			return c as Interactable
	return null

## 프롬프트 대상: E로 쓸 수 있는 대상이 있으면 그것(E를 누르면 실제로 처리되는 대상), 없으면 가장 가까운 타격형 대상.
func _focus_target() -> Interactable:
	var hits := _sweep()
	var key := _first_key_target(hits)
	if key != null:
		return key
	for c in hits:
		if c is Interactable and (c as Interactable).can_interact():
			return c as Interactable
	return null

func _update_focus() -> void:
	var target := _focus_target()
	var prompt := target.prompt_message if target != null else ""
	if prompt != _prompt:
		_prompt = prompt
		focus_changed.emit(prompt)

## 가장 가까운 공격 가능 대상(적 / 타격형 채집물) 하나만 처리
func _resolve_attack() -> void:
	for c in _sweep():
		if c is Harvestable:
			var h := c as Harvestable
			if h.harvest_by_hit and h.can_interact():
				var tool_type: StringName = equipped.tool_type if equipped != null else &""
				var tool_tier: int = equipped.tool_tier if equipped != null else 0
				h.hit(self, tool_type, tool_tier)
				return
		elif c.is_in_group(&"enemy"):
			c.call("take_damage", _current_damage(), global_position)
			return

# ---------------------------------------------------------------- 장착·연출

func _on_inventory_updated() -> void:
	if equipped != null and not inventory.has_item(equipped.id):
		_set_equipped(null)

func _set_equipped(item: ItemData) -> void:
	equipped = item
	_refresh_tool_mesh()
	equipped_changed.emit(item)

## 장착 도구 플레이스홀더(BoxMesh 조합). 도구 메시가 에셋이 되면 교체한다.
func _refresh_tool_mesh() -> void:
	if _tool_socket == null:
		return
	for c in _tool_socket.get_children():
		c.queue_free()
	if equipped == null:
		return
	var wood := Color("#876C46")
	var stone := Color("#9BA7A6")
	# ToolSocket은 회전 없는 손 중심. 도구는 손에서 위(+Y)로 뻗는다.
	match equipped.tool_type:
		&"axe":
			_add_box(Vector3(0.05, 0.45, 0.05), Vector3(0, 0.2, 0), wood)
			_add_box(Vector3(0.04, 0.14, 0.18), Vector3(0, 0.4, 0.07), stone)
		&"pickaxe":
			_add_box(Vector3(0.05, 0.45, 0.05), Vector3(0, 0.2, 0), wood)
			_add_box(Vector3(0.04, 0.08, 0.34), Vector3(0, 0.42, 0), stone)
		&"spear":
			_add_box(Vector3(0.04, 0.9, 0.04), Vector3(0, 0.35, 0), wood)
			_add_box(Vector3(0.05, 0.14, 0.05), Vector3(0, 0.85, 0), stone)

func _add_box(size: Vector3, pos: Vector3, color: Color) -> void:
	var m := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	m.mesh = box
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.85
	m.material_override = mat
	m.position = pos
	_tool_socket.add_child(m)

func _play_swing() -> void:
	if _arm_r == null:
		return
	if _swing_tween != null:
		_swing_tween.kill()
	_arm_r.rotation.x = deg_to_rad(80.0)       # 뒤로 치켜들었다가(+X 회전 = 팔이 뒤로) 앞으로 내려친다
	_swing_tween = create_tween()
	_swing_tween.tween_property(_arm_r, "rotation:x", deg_to_rad(-40.0), 0.2)
	_swing_tween.tween_property(_arm_r, "rotation:x", 0.0, 0.15)

func _animate_walk(delta: float, moving: bool) -> void:
	_anim_amp = lerpf(_anim_amp, 1.0 if moving else 0.0, 1.0 - exp(-12.0 * delta))
	if moving:
		_anim_t += delta * 12.0
	var swing := sin(_anim_t) * deg_to_rad(25.0) * _anim_amp
	if _leg_l != null:
		_leg_l.rotation.x = swing
	if _leg_r != null:
		_leg_r.rotation.x = -swing
	if _arm_l != null:
		_arm_l.rotation.x = -swing
	if _arm_r != null and (_swing_tween == null or not _swing_tween.is_running()):
		_arm_r.rotation.x = swing
	if _body != null:
		_body.position.y = _body_base_y + absf(sin(_anim_t)) * 0.03 * _anim_amp

func _on_vitals_died() -> void:
	_dead = true
	set_input_enabled(false)
	var tw := create_tween()
	tw.tween_property(_visual, "rotation:x", deg_to_rad(90.0), 0.6)
	tw.tween_callback(func() -> void: player_died.emit())
