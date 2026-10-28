extends PanelContainer
# 5×4 그리드. 설계: docs/architecture/worldclock-ui.md

const SLOT_SCENE := preload("res://scenes/ui/slot_widget.tscn")

var _inventory: InventoryData
var _player: Player
var _slots: Array[SlotWidget] = []

@onready var _grid: GridContainer = $VBox/Grid

func _ready() -> void:
	for i in 20:
		var s := SLOT_SCENE.instantiate() as SlotWidget
		s.index = i
		_grid.add_child(s)
		_slots.append(s)

func bind(inventory: InventoryData, player: Player) -> void:
	_inventory = inventory
	_player = player
	for s in _slots:
		s.clicked.connect(_on_slot_clicked)
	inventory.inventory_updated.connect(_refresh)
	player.equipped_changed.connect(func(_item: ItemData) -> void: _refresh())
	_refresh()

func _on_slot_clicked(index: int) -> void:
	_player.use_slot(index)

func _refresh() -> void:
	for i in _slots.size():
		var slot := _inventory.get_slot(i)
		if slot == null or slot.is_empty():
			_slots[i].set_slot(null, 0)
			_slots[i].set_highlight(false)
		else:
			_slots[i].set_slot(slot.item, slot.quantity)
			_slots[i].set_highlight(_player.equipped != null and _player.equipped.id == slot.item.id)
