extends Node3D

var _capture: bool = "--capture" in OS.get_cmdline_user_args()

@onready var island: IslandGenerator = $Island
@onready var player: Player = $Player
@onready var camera_rig: CameraRig = $CameraRig
@onready var hud: HUD = $HUD
@onready var spawner: EnemySpawner = $EnemySpawner
@onready var _world_env: WorldEnvironment = $WorldEnvironment
@onready var _sun: DirectionalLight3D = $Sun
@onready var _water: MeshInstance3D = $Water

func _ready() -> void:
	player.process_mode = Node.PROCESS_MODE_DISABLED     # 섬이 생기기 전에는 플레이어를 멈춰 둔다
	WorldClock.reset()
	var env := _world_env.environment
	WorldClock.register_lighting(env, _sun, env.sky.sky_material as ProceduralSkyMaterial, _water.get_surface_override_material(0) as ShaderMaterial)
	hud.panels_changed.connect(camera_rig.set_ui_open)
	player.player_died.connect(_on_player_died)
	if _capture:
		camera_rig.set_input_enabled(false)              # CameraRig._ready가 먼저 캡처하므로 여기서 푼다
	island.generated.connect(_on_island_generated)
	island.generate()

func _on_island_generated(spawn_point: Vector3) -> void:
	player.global_position = spawn_point
	player.velocity = Vector3.ZERO
	camera_rig.set_pose(camera_rig.default_yaw_deg, camera_rig.default_pitch_deg, camera_rig.default_distance)
	player.face_direction(camera_rig.get_forward())
	player.process_mode = Node.PROCESS_MODE_INHERIT
	hud.bind(player)
	if _capture:
		_run_capture()                                   # 캡처에서는 적 스포너를 켜지 않는다(화면 비교 결정성)
	else:
		spawner.activate(island, player)

func _on_player_died() -> void:
	hud.show_death()
	await get_tree().create_timer(2.5).timeout
	get_tree().reload_current_scene()

## godot --path . -- --capture : 고정 자세로 낮/밤 화면을 captures/에 저장하고 종료한다. 헤드리스에서는 이미지가 비므로 쓰지 않는다.
func _run_capture() -> void:
	var yaw := _pick_capture_yaw(35.0, -35.0, 7.0)
	camera_rig.set_pose(yaw, -35.0, 7.0)
	player.face_direction(camera_rig.get_forward())
	await _wait_frames(60)                               # 내비·셰이더 컴파일 안정화, SpringArm 충돌 반영
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://captures"))
	WorldClock.running = false
	WorldClock.set_time(0.25, true)                      # 12:00
	await _wait_frames(10)
	get_viewport().get_texture().get_image().save_png("res://captures/day.png")
	await _capture_overview()                            # 같은 12:00, 섬 전체 모양
	WorldClock.set_time(0.80, true)                      # 01:12
	await _wait_frames(10)
	get_viewport().get_texture().get_image().save_png("res://captures/night.png")
	print("CAPTURED res://captures/day.png res://captures/overview.png res://captures/night.png")
	get_tree().quit()

## 기본 yaw(35°)부터 ±20°씩 벌려 가며, 피벗→카메라 선분에서 5 m 안에 나무 수관(소나무·야자수)이 없는 첫 yaw를 고른다.
## 수관에는 충돌이 없어 SpringArm이 밀어 주지 못하므로, 카메라가 잎 속에 들어간 캡처를 피하기 위한 선택이다. 시드가 같으면 결과도 같다.
func _pick_capture_yaw(base_yaw: float, pitch: float, distance: float) -> float:
	var pivot := player.global_position + Vector3.UP * camera_rig.pivot_height
	var crowns: Array[Vector3] = []
	for prop in island.get_node("Props").get_children():
		if prop.name.begins_with("PineTree") or prop.name.begins_with("PalmTree"):
			crowns.append((prop as Node3D).global_position + Vector3.UP * 2.2)
	for k in 18:
		var yaw := base_yaw + float((k + 1) >> 1) * 20.0 * (1.0 if k % 2 == 1 else -1.0)
		var fwd := Vector3(-sin(deg_to_rad(yaw)), 0.0, -cos(deg_to_rad(yaw)))
		var cam := pivot - fwd * distance * cos(deg_to_rad(-pitch)) + Vector3.UP * distance * sin(deg_to_rad(-pitch))
		var clear := true
		for c in crowns:
			var closest := Geometry3D.get_closest_point_to_segment(c, pivot, cam)
			if closest.distance_to(c) < 5.0:
				clear = false
				break
		if clear:
			print("capture yaw=", yaw)
			return yaw
	return base_yaw

## 카메라 (0, 70, 45)에서 원점을 내려다본 개요(HUD 숨김). 다음 튜닝 때 비교 기준이 된다.
func _capture_overview() -> void:
	var cam := Camera3D.new()
	add_child(cam)
	cam.fov = 50.0                                       # 게임 카메라와 같은 FOV. 기본 75°면 먼 모서리에서 물 평면(400 m) 끝이 보인다
	cam.position = Vector3(0.0, 70.0, 45.0)
	cam.look_at(Vector3.ZERO)
	cam.make_current()
	hud.visible = false
	await _wait_frames(10)
	get_viewport().get_texture().get_image().save_png("res://captures/overview.png")
	hud.visible = true
	cam.queue_free()
	camera_rig.get_node("Pitch/SpringArm/Camera3D").make_current()
	await _wait_frames(2)

func _wait_frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame
