class_name CameraRig extends Node3D
# 마우스로 도는 3인칭 궤도 카메라. 마우스 캡처 상태는 이 노드만 바꾼다.
# 설계: docs/architecture/player-vitals-interaction.md (CameraRig 절), 수치 원본: docs/gdd.md 카메라 표

@export var target_path: NodePath
@export var follow_speed: float = 10.0
@export var pivot_height: float = 0.9
@export var default_yaw_deg: float = 35.0
@export var default_pitch_deg: float = -35.0
@export var min_pitch_deg: float = -70.0
@export var max_pitch_deg: float = -5.0
@export var default_distance: float = 7.0
@export var min_distance: float = 3.0
@export var max_distance: float = 12.0
@export var zoom_step: float = 0.75
@export var zoom_speed: float = 10.0
@export var mouse_sensitivity: float = 0.15      # 도/픽셀

var _yaw: float = 0.0                            # 라디안
var _pitch: float = 0.0
var _target_distance: float = 7.0
var _ui_open: bool = false
var _input_enabled: bool = true
var _target: Node3D

@onready var _pitch_node: Node3D = $Pitch
@onready var _arm: SpringArm3D = $Pitch/SpringArm

func _ready() -> void:
	top_level = true
	_target = get_node_or_null(target_path) as Node3D
	set_pose(default_yaw_deg, default_pitch_deg, default_distance)
	_apply_mouse_mode()

func get_yaw() -> float:
	return _yaw

## 수평 정면 = (−sin yaw, 0, −cos yaw)
func get_forward() -> Vector3:
	return Vector3(-sin(_yaw), 0.0, -cos(_yaw))

## 각도·거리(목표·현재 모두) 즉시 적용 + 위치를 타깃으로 스냅
func set_pose(yaw_deg: float, pitch_deg: float, distance: float) -> void:
	_yaw = deg_to_rad(yaw_deg)
	_pitch = clampf(deg_to_rad(pitch_deg), deg_to_rad(min_pitch_deg), deg_to_rad(max_pitch_deg))
	_target_distance = clampf(distance, min_distance, max_distance)
	rotation.y = _yaw
	_pitch_node.rotation.x = _pitch
	_arm.spring_length = _target_distance
	if _target != null:
		global_position = _target.global_position + Vector3.UP * pivot_height

func set_ui_open(open: bool) -> void:
	_ui_open = open
	_apply_mouse_mode()

## false: 마우스 VISIBLE, 회전·줌·재캡처 입력 무시 (캡처 모드)
func set_input_enabled(enabled: bool) -> void:
	_input_enabled = enabled
	_apply_mouse_mode()

func _apply_mouse_mode() -> void:
	if not _input_enabled or _ui_open:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	else:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(delta: float) -> void:
	if _target != null:
		global_position = global_position.lerp(_target.global_position + Vector3.UP * pivot_height, 1.0 - exp(-follow_speed * delta))
	_arm.spring_length = lerpf(_arm.spring_length, _target_distance, 1.0 - exp(-zoom_speed * delta))

func _unhandled_input(event: InputEvent) -> void:
	if not _input_enabled:
		return
	var captured := Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	if event is InputEventMouseMotion:
		if captured:
			var rel := (event as InputEventMouseMotion).screen_relative
			_yaw -= deg_to_rad(rel.x * mouse_sensitivity)
			_pitch = clampf(_pitch - deg_to_rad(rel.y * mouse_sensitivity), deg_to_rad(min_pitch_deg), deg_to_rad(max_pitch_deg))
			rotation.y = _yaw
			_pitch_node.rotation.x = _pitch
	elif event.is_action_pressed("camera_zoom_in"):
		if captured:
			_target_distance = clampf(_target_distance - zoom_step, min_distance, max_distance)
	elif event.is_action_pressed("camera_zoom_out"):
		if captured:
			_target_distance = clampf(_target_distance + zoom_step, min_distance, max_distance)
	elif event.is_action_pressed("ui_cancel"):
		# 패널이 열려 있으면 HUD가 먼저 처리한다. 여기는 패널이 없고 캡처 중일 때만.
		if captured and not _ui_open:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			get_viewport().set_input_as_handled()
	elif event.is_action_pressed("attack"):
		if not captured and not _ui_open:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
			get_viewport().set_input_as_handled()

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and _input_enabled and not _ui_open:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
