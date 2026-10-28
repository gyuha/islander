extends PanelContainer
# 레시피 목록 + 제작 버튼. 설계: docs/architecture/worldclock-ui.md

const ROW_SCENE := preload("res://scenes/ui/recipe_row.tscn")

var _rows: Array[Node] = []

@onready var _rows_box: VBoxContainer = $VBox/Rows

func bind(crafting: CraftingProcessor, inventory: InventoryData) -> void:
	for recipe in crafting.recipes:
		var row := ROW_SCENE.instantiate()
		_rows_box.add_child(row)
		row.setup(recipe, crafting)
		_rows.append(row)
	inventory.inventory_updated.connect(_refresh)
	crafting.recipe_unlocked.connect(func(_id: StringName) -> void: _refresh())
	crafting.crafted.connect(func(_id: StringName) -> void: _refresh())

func _refresh() -> void:
	for row in _rows:
		row.refresh()
