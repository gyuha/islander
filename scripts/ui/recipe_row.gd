extends HBoxContainer
# 레시피 한 줄: [결과 슬롯] [이름 + 재료 "필요/보유"] [제작 버튼]. 설계: docs/architecture/worldclock-ui.md

const SHORT_COLOR := "#C0392B"

var _recipe: Dictionary
var _crafting: CraftingProcessor

@onready var _result: SlotWidget = $Result
@onready var _name: Label = $Info/NameLabel
@onready var _ingredients: RichTextLabel = $Info/Ingredients
@onready var _button: Button = $CraftButton

func setup(recipe: Dictionary, crafting: CraftingProcessor) -> void:
	_recipe = recipe
	_crafting = crafting
	_button.pressed.connect(func() -> void: _crafting.craft(_recipe["id"]))
	refresh()

func refresh() -> void:
	var result_item := ItemDB.get_item(_recipe["result"])
	var unlocked := _crafting.is_unlocked(_recipe["id"])
	_result.set_slot(result_item, int(_recipe["amount"]))
	_result.modulate = Color.WHITE if unlocked else Color("#00000080")
	_name.text = result_item.name if unlocked else "???"
	if not unlocked:
		_ingredients.text = "재료를 더 찾아보세요"
		_button.disabled = true
		return
	var parts: Array[String] = []
	for ing_id: StringName in _recipe["ingredients"]:
		var need: int = _recipe["ingredients"][ing_id]
		var have := _crafting.inventory.count_of(ing_id)
		var token := "%s %d/%d" % [ItemDB.get_item(ing_id).name, need, have]
		parts.append(token if have >= need else "[color=%s]%s[/color]" % [SHORT_COLOR, token])
	_ingredients.text = " · ".join(parts)
	_button.disabled = not _crafting.can_craft(_recipe["id"])
