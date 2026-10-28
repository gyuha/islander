class_name Harvestable extends Interactable
# 나무·바위(LMB 타격)와 베리 덤불(E)의 채집 로직. 설계: docs/architecture/player-vitals-interaction.md

signal harvested(item_id: StringName, amount: int)
signal depleted
signal respawned

@export var item_id: StringName = &"wood"
@export var preferred_tool: StringName = &"axe"
@export var max_hp: int = 6
@export var base_yield: int = 1
@export var interact_yield: int = 3          # harvest_by_hit = false 일 때
@export var respawn_sec: float = 90.0
@export var harvest_by_hit: bool = true      # 나무·바위 true(LMB), 베리 false(E)
@export var deplete_node_name: String = "Model"   # 고갈 시 숨길 노드 이름 (베리: "Berries"), find_child로 찾음

var hp: int
var _depleted: bool = false
var _interact_left: int = -1             # 베리처럼 E로 따는 대상의 남은 수확량(-1 = 아직 시작 안 함)
var _model: Node3D
var _deplete_node: Node3D
var _blocker_shape: CollisionShape3D

static func calc_yield(base: int, tool_type: StringName, tool_tier: int, preferred: StringName) -> int:
	return base * (3 if tool_type == preferred and tool_tier >= 1 else 1)

static func calc_node_damage(tool_type: StringName, tool_tier: int, preferred: StringName) -> int:
	return 2 if tool_type == preferred and tool_tier >= 1 else 1

func _ready() -> void:
	hp = max_hp
	_model = find_child("Model", true, false) as Node3D
	_deplete_node = find_child(deplete_node_name, true, false) as Node3D
	var blocker := find_child("Blocker", true, false)
	if blocker != null:
		_blocker_shape = blocker.find_child("CollisionShape3D", true, false) as CollisionShape3D

func can_interact() -> bool:
	return not _depleted

## E 키로 쓸 수 있는가. 타격형(나무·바위)은 LMB 전용이라 E 대상이 아니다.
func usable_with_key() -> bool:
	return can_interact() and not harvest_by_hit

## 인벤토리가 가득 찬 경우의 규칙:
## - 하나도 못 넣으면 아무 일도 없다(노드 피해·고갈 없음. 토스트는 Player.receive_item의 inventory_full이 띄운다).
## - 타격형은 전량이 들어갈 때만 노드가 피해를 입는다. 일부만 들어가면 들어간 만큼 주되 피해는 없다(남은 몫은 노드에 남음).
## - E형(베리)은 남은 수확량을 세어, 일부만 따면 그만큼 줄이고 0이 되면 고갈한다.
func hit(user: Node, tool_type: StringName, tool_tier: int) -> void:
	if _depleted or not harvest_by_hit:
		return
	var amount := calc_yield(base_yield, tool_type, tool_tier, preferred_tool)
	var left: int = user.call("receive_item", item_id, amount)
	var given := amount - left
	if given > 0:
		harvested.emit(item_id, given)
	if left > 0:
		return
	hp -= calc_node_damage(tool_type, tool_tier, preferred_tool)
	if hp <= 0:
		_deplete()
	else:
		_play_hit()

func _on_interact(user: Node) -> void:
	if _depleted or harvest_by_hit:
		return
	if _interact_left < 0:
		_interact_left = interact_yield
	var left: int = user.call("receive_item", item_id, _interact_left)
	var given := _interact_left - left
	if given > 0:
		harvested.emit(item_id, given)
	_interact_left = left
	if _interact_left <= 0:
		_interact_left = -1
		_deplete()

func _play_hit() -> void:
	if _model == null:
		return
	var tw := create_tween()
	tw.tween_property(_model, "scale", Vector3.ONE * 0.9, 0.06)
	tw.tween_property(_model, "scale", Vector3.ONE, 0.06)

func _deplete() -> void:
	_depleted = true
	if _blocker_shape != null:
		_blocker_shape.set_deferred("disabled", true)
	if _deplete_node != null:
		var tw := create_tween()
		tw.tween_property(_deplete_node, "scale", Vector3.ZERO, 0.3)
		tw.tween_callback(func() -> void: _deplete_node.visible = false)
	depleted.emit()
	await get_tree().create_timer(respawn_sec).timeout
	_respawn()

func _respawn() -> void:
	_depleted = false
	hp = max_hp
	_interact_left = -1
	if _blocker_shape != null:
		_blocker_shape.disabled = false
	if _deplete_node != null:
		_deplete_node.scale = Vector3.ONE
		_deplete_node.visible = true
	respawned.emit()
