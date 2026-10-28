class_name Slime extends Enemy
# 밤에만 스폰, 아침에 녹는다. 설계: docs/architecture/enemies-ai.md

@export var detect_range: float = 20.0
@export var give_up_range: float = 28.0
@export var wander_radius: float = 4.0

var rng_seed: int = 0                     # 스포너가 add_child 전에 지정(스포너 시드 + 스폰 번호)
var _wander_left: float = 0.0
var _anim_t: float = 0.0
var _rng := RandomNumberGenerator.new()
var _model: Node3D
var _body: Node3D

func _ready() -> void:
	super()
	_rng.seed = rng_seed
	_model = visual.find_child("Model", true, false) as Node3D
	_body = visual.find_child("Body", true, false) as Node3D

func _should_chase(dist: float) -> bool:
	return dist <= detect_range

func _should_give_up(dist: float) -> bool:
	return dist > give_up_range

## 2~4초마다 현재 위치 4 m 이내 임의 점으로 이동
func _idle_update(delta: float) -> void:
	if not _nav_ready:
		return
	_wander_left -= delta
	if _wander_left > 0.0:
		return
	_wander_left = _rng.randf_range(2.0, 4.0)
	var angle := _rng.randf() * TAU
	var p := global_position + Vector3(cos(angle), 0.0, sin(angle)) * _rng.randf_range(1.0, wander_radius)
	nav.move_to(NavigationServer3D.map_get_closest_point(nav.get_navigation_map(), p))

## 이동 중 스쿼시 앤 스트레치(y 스케일 1 + 0.15·sin(t·10), xz 반대)와 깡충(0.15 m)
func _visual_update(delta: float, moving: bool) -> void:
	if moving:
		_anim_t += delta
	var amp := 1.0 if moving else 0.0
	if _body != null:
		var s := sin(_anim_t * 10.0) * 0.15 * amp
		_body.scale = _body.scale.lerp(Vector3(1.0 - s * 0.5, 1.0 + s, 1.0 - s * 0.5), 0.5)
	if _model != null:
		_model.position.y = lerpf(_model.position.y, absf(sin(_anim_t * 5.0)) * 0.15 * amp, 0.5)
