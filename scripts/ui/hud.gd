class_name HUD extends CanvasLayer
# 체력·배고픔 바, 시계, 프롬프트, 토스트, 굶주림 경고, 장착 아이콘, 사망 문구, 패널 토글.
# 설계: docs/architecture/worldclock-ui.md. 마우스 모드는 직접 바꾸지 않고 panels_changed만 내보낸다.

signal panels_changed(any_open: bool)   # 열린 패널 수가 0↔1 이상으로 바뀔 때만

const EMPTY_EQUIP_ALPHA := 0.35          # 장착 아이템이 없을 때 장착 슬롯을 흐리게

var _player: Player
var _any_open: bool = false
var _dead: bool = false
var _toast_tween: Tween
var _warn_tween: Tween

@onready var _health_bar: ProgressBar = $TopLeft/HealthBar
@onready var _hunger_bar: ProgressBar = $TopLeft/HungerBar
@onready var _day_label: Label = $TopRight/DayLabel
@onready var _clock_label: Label = $TopRight/ClockLabel
@onready var _prompt: Label = $Prompt
@onready var _toast: Label = $Toast
@onready var _equipped: SlotWidget = $Equipped
@onready var _inventory_panel: PanelContainer = $InventoryPanel
@onready var _crafting_panel: PanelContainer = $CraftingPanel
@onready var _death_label: Label = $DeathLabel
@onready var _vignette: TextureRect = $Vignette

func _ready() -> void:
	_toast.modulate.a = 0.0
	_equipped.modulate.a = EMPTY_EQUIP_ALPHA
	WorldClock.time_changed.connect(_on_time_changed)
	_on_time_changed(WorldClock.time_of_day, WorldClock.day)

## Main이 호출: Vitals/Player/Inventory/Crafting 시그널 연결
func bind(player: Player) -> void:
	_player = player
	var v := player.vitals
	v.vitals_changed.connect(_on_vitals_changed)
	v.starving_changed.connect(_on_starving_changed)
	_on_vitals_changed(v.health, v.max_health, v.hunger, v.max_hunger)
	player.focus_changed.connect(func(text: String) -> void: _prompt.text = text)
	player.item_received.connect(func(item: ItemData, amount: int) -> void: _show_toast("+%d %s" % [amount, item.name]))
	player.inventory_full.connect(func() -> void: _show_toast("가방이 가득 찼어요"))
	player.notice.connect(_show_toast)
	v.died.connect(_on_player_dead)
	player.equipped_changed.connect(_on_equipped_changed)
	var c := player.crafting
	c.recipe_unlocked.connect(func(id: StringName) -> void: _show_toast("새 레시피! %s" % ItemDB.get_item(c.get_recipe(id)["result"]).name))
	c.crafted.connect(func(id: StringName) -> void: _show_toast("%s 제작!" % ItemDB.get_item(c.get_recipe(id)["result"]).name))
	c.craft_failed.connect(_on_craft_failed)
	_inventory_panel.bind(player.inventory, player)
	_crafting_panel.bind(c, player.inventory)

func show_death() -> void:
	_death_label.visible = true

## 사망하면 열린 패널을 닫고, 이후 Tab/C로 패널을 열 수 없다.
func _on_player_dead() -> void:
	_dead = true
	_inventory_panel.visible = false
	_crafting_panel.visible = false
	_update_any_open()

func _unhandled_input(event: InputEvent) -> void:
	if _dead:
		return
	if event.is_action_pressed("toggle_inventory"):
		_set_panel(_inventory_panel, not _inventory_panel.visible)
	elif event.is_action_pressed("toggle_crafting"):
		_set_panel(_crafting_panel, not _crafting_panel.visible)
	elif event.is_action_pressed("ui_cancel") and _any_open:
		# 패널이 열려 있을 때만 처리한다. 없으면 CameraRig가 마우스를 해제한다.
		_inventory_panel.visible = false
		_crafting_panel.visible = false
		_update_any_open()
		get_viewport().set_input_as_handled()
		return
	else:
		return
	get_viewport().set_input_as_handled()

func _set_panel(panel: Control, open: bool) -> void:
	panel.visible = open
	_update_any_open()

func _update_any_open() -> void:
	var any_open := _inventory_panel.visible or _crafting_panel.visible
	if any_open != _any_open:
		_any_open = any_open
		panels_changed.emit(any_open)

func _on_vitals_changed(health: float, max_health: float, hunger: float, max_hunger: float) -> void:
	_health_bar.max_value = max_health
	_health_bar.value = health
	_hunger_bar.max_value = max_hunger
	_hunger_bar.value = hunger

func _on_starving_changed(is_starving: bool) -> void:
	if _warn_tween != null:
		_warn_tween.kill()
	if is_starving:
		_warn_tween = create_tween().set_loops()
		_warn_tween.tween_property(_vignette, "modulate:a", 0.6, 0.5)
		_warn_tween.parallel().tween_property(_hunger_bar, "modulate:a", 0.45, 0.5)
		_warn_tween.tween_property(_vignette, "modulate:a", 0.0, 0.5)
		_warn_tween.parallel().tween_property(_hunger_bar, "modulate:a", 1.0, 0.5)
	else:
		_vignette.modulate.a = 0.0
		_hunger_bar.modulate.a = 1.0

func _on_time_changed(_time_of_day: float, day: int) -> void:
	_day_label.text = "%d일차" % day
	_clock_label.text = "%s %s" % [WorldClock.get_clock_text(), "밤" if WorldClock.is_night else "낮"]

func _on_equipped_changed(item: ItemData) -> void:
	_equipped.set_slot(item, 1)
	_equipped.modulate.a = 1.0 if item != null else EMPTY_EQUIP_ALPHA

func _on_craft_failed(_id: StringName, reason: StringName) -> void:
	match reason:
		&"missing": _show_toast("재료가 부족해요")
		&"no_space": _show_toast("가방이 가득 찼어요")
		_: _show_toast("아직 만들 수 없어요")

## 1.5초 후 페이드
func _show_toast(text: String) -> void:
	if _toast_tween != null:
		_toast_tween.kill()
	_toast.text = text
	_toast.modulate.a = 1.0
	_toast_tween = create_tween()
	_toast_tween.tween_interval(1.0)
	_toast_tween.tween_property(_toast, "modulate:a", 0.0, 0.5)
