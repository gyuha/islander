# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/genre_survival_status_depletion_manager.gd
# Modified for dongval: StatusDepletionManager → Vitals, 갈증 삭제, 체력·회복·섭취·피해 추가, 활동 열거형(sprinting 대체),
#   매 프레임 시그널 → 표시값(올림 정수)이 바뀔 때만, 처리 본체를 tick(delta)로 분리(테스트에서 직접 호출)
class_name Vitals extends Node

enum Activity { IDLE, WALK, SPRINT }

signal vitals_changed(health: float, max_health: float, hunger: float, max_hunger: float)
signal starving_changed(is_starving: bool)     # hunger ≤ warn_hunger 진입/이탈 시
signal damaged(amount: float)
signal died

@export var max_health: float = 100.0
@export var max_hunger: float = 100.0
@export var hunger_rate: float = 0.25
@export var activity_multipliers: Dictionary = { Activity.IDLE: 0.5, Activity.WALK: 1.0, Activity.SPRINT: 3.0 }
@export var starve_damage_per_sec: float = 1.0
@export var warn_hunger: float = 25.0
@export var regen_hunger_threshold: float = 60.0
@export var regen_delay: float = 5.0
@export var regen_per_sec: float = 0.5

var activity: Activity = Activity.IDLE
var health: float = 100.0
var hunger: float = 100.0
var is_dead: bool = false

var _since_damage: float = 999.0
var _starving: bool = false
var _shown_health: int = -1
var _shown_hunger: int = -1

func _ready() -> void:
	health = max_health
	hunger = max_hunger
	_emit_if_changed()

func _physics_process(delta: float) -> void:
	tick(delta)

func tick(delta: float) -> void:
	if is_dead:
		return
	_since_damage += delta
	hunger = clampf(hunger - hunger_rate * float(activity_multipliers[activity]) * delta, 0.0, max_hunger)
	if hunger <= 0.0:
		health -= starve_damage_per_sec * delta
	elif hunger >= regen_hunger_threshold and _since_damage >= regen_delay:
		health = minf(health + regen_per_sec * delta, max_health)
	if health <= 0.0:
		_die()
		return
	_emit_if_changed()

## "hunger", "health" 키를 더하고 clamp.
func eat(consumables: Dictionary) -> void:
	if is_dead:
		return
	hunger = clampf(hunger + float(consumables.get("hunger", 0.0)), 0.0, max_hunger)
	health = clampf(health + float(consumables.get("health", 0.0)), 0.0, max_health)
	_emit_if_changed()

func take_damage(amount: float) -> void:
	if is_dead or amount <= 0.0:
		return
	health -= amount
	_since_damage = 0.0
	damaged.emit(amount)
	if health <= 0.0:
		_die()
		return
	_emit_if_changed()

func _die() -> void:
	health = 0.0
	is_dead = true
	_emit_if_changed()
	died.emit()

func _emit_if_changed() -> void:
	var starving := hunger <= warn_hunger
	if starving != _starving:
		_starving = starving
		starving_changed.emit(starving)
	var h := ceili(health)
	var f := ceili(hunger)
	if h != _shown_health or f != _shown_hunger:
		_shown_health = h
		_shown_hunger = f
		vitals_changed.emit(health, max_health, hunger, max_hunger)
