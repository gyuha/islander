extends Node
# Autoload "WorldClock" — 시간 소유, 낮/밤 조명 보간. 설계: docs/architecture/worldclock-ui.md
# class_name을 붙이지 않는다(싱글턴 이름과 충돌).

signal time_changed(time_of_day: float, day: int)   # 최대 4Hz
signal phase_changed(is_night: bool)
signal day_started(day: int)

@export var day_length_sec: float = 360.0
@export var night_start: float = 0.6667            # 22:00
@export var start_time: float = 0.0833             # 08:00
@export var transition_sec: float = 12.0
@export var time_scale: float = 1.0

var time_of_day: float = 0.0833                    # 0..1, 0 = 06:00
var day: int = 1
var is_night: bool = false
var running: bool = true

# docs/art/style-guide.md 4절 "낮/밤 조명 값"
const DAY := {
	"sun_color": Color("#FFF3DE"), "sun_energy": 1.0,
	"ambient_color": Color("#CFEDEA"), "ambient_energy": 0.48,
	"sky_top": Color("#8ED3E0"), "sky_horizon": Color("#C9EEF0"), "sky_ground_bottom": Color("#47A693"),
	"water_shallow": Color("#7FD3C4"), "water_deep": Color("#47A693"), "water_foam": Color("#EAF8F3"),
}
const NIGHT := {
	"sun_color": Color("#9DB8FF"), "sun_energy": 0.3,
	"ambient_color": Color("#2E6B78"), "ambient_energy": 0.55,
	"sky_top": Color("#0A2E3A"), "sky_horizon": Color("#145A5C"), "sky_ground_bottom": Color("#0B4F4C"),
	"water_shallow": Color("#1C8A7A"), "water_deep": Color("#0B6965"), "water_foam": Color("#9FD9CF"),
}

var _env: Environment
var _sun: DirectionalLight3D
var _sky: ProceduralSkyMaterial
var _water: ShaderMaterial
var _tween: Tween
var _since_emit: float = 0.0

func _ready() -> void:
	reset()

## 씬 재시작 시 Main이 호출. 이전 씬의 조명 참조는 버린다.
func reset() -> void:
	if _tween != null:
		_tween.kill()
	_env = null
	_sun = null
	_sky = null
	_water = null
	time_of_day = start_time
	day = 1
	running = true
	is_night = time_of_day >= night_start
	_since_emit = 0.0

func _process(delta: float) -> void:
	if not running:
		return
	time_of_day += delta * time_scale / day_length_sec
	if time_of_day >= 1.0:
		time_of_day -= 1.0
		day += 1
		day_started.emit(day)
	_update_phase(false)
	_since_emit += delta
	if _since_emit >= 0.25:
		_since_emit = 0.0
		time_changed.emit(time_of_day, day)

## 디버그·캡처용. instant면 조명을 즉시 적용한다.
func set_time(t: float, instant: bool = false) -> void:
	time_of_day = clampf(t, 0.0, 0.9999)
	_update_phase(instant)
	if instant:
		_apply_phase(is_night, 0.0)
	time_changed.emit(time_of_day, day)

## "HH:MM", hour = (6 + t*24) mod 24
func get_clock_text() -> String:
	var total_min := int(floor(fposmod(6.0 + time_of_day * 24.0, 24.0) * 60.0))
	return "%02d:%02d" % [floori(total_min / 60.0), total_min % 60]

func register_lighting(env: Environment, sun: DirectionalLight3D, sky: ProceduralSkyMaterial, water: ShaderMaterial) -> void:
	_env = env
	_sun = sun
	_sky = sky
	_water = water
	_apply_phase(is_night, 0.0)

func _update_phase(instant: bool) -> void:
	var night := time_of_day >= night_start
	if night != is_night:
		is_night = night
		phase_changed.emit(is_night)
		if not instant:
			_apply_phase(is_night, transition_sec)

## genre_survival_survival_patterns.gd의 transition_to_night(Environment 속성 Tween) 패턴을 확장.
func _apply_phase(night: bool, duration: float) -> void:
	if _tween != null:
		_tween.kill()
	if _env == null:
		return                                      # register_lighting 전에는 조명을 건드리지 않는다
	var v: Dictionary = NIGHT if night else DAY
	var targets: Array = [
		[_sun, "light_color", v["sun_color"]], [_sun, "light_energy", v["sun_energy"]],
		[_env, "ambient_light_color", v["ambient_color"]], [_env, "ambient_light_energy", v["ambient_energy"]],
		[_sky, "sky_top_color", v["sky_top"]], [_sky, "sky_horizon_color", v["sky_horizon"]],
		[_sky, "ground_horizon_color", v["sky_horizon"]], [_sky, "ground_bottom_color", v["sky_ground_bottom"]],
		[_water, "shader_parameter/shallow_color", v["water_shallow"]], [_water, "shader_parameter/deep_color", v["water_deep"]],
		[_water, "shader_parameter/foam_color", v["water_foam"]],
	]
	if duration <= 0.0:
		for t in targets:
			if t[0] != null:
				(t[0] as Object).set(t[1], t[2])
		return
	_tween = create_tween().set_parallel(true)
	for t in targets:
		if t[0] != null:
			_tween.tween_property(t[0], t[1], t[2], duration)
