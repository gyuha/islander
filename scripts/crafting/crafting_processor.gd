# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/genre_survival_crafting_recipe_processor.gd (흐름만)
# Modified for dongval: CraftingRecipeProcessor → CraftingProcessor, 전부 확인 → 소모 → 지급 흐름 유지,
#   _has_item/_consume_item을 InventoryData로 구현, ModularInventoryController·ResourceLoader 의존 제거(id 기반 조회 Callable 주입), 발견(해금) 시스템 추가
class_name CraftingProcessor extends Node

signal recipe_unlocked(recipe_id: StringName)
signal crafted(recipe_id: StringName)
signal craft_failed(recipe_id: StringName, reason: StringName)   # &"locked", &"missing", &"no_space"

var inventory: InventoryData
var recipes: Array[Dictionary] = []
var discovered: Dictionary = {}          # item_id(StringName) → true
var _unlocked: Dictionary = {}           # recipe_id(StringName) → true
var _lookup: Callable                    # func(id: StringName) -> ItemData

## 레시피 JSON을 파싱한다. 알 수 없는 아이템 id, 수량 ≤ 0인 레시피는 push_error 후 건너뛴다.
## 반환 항목: { "id": StringName, "result": StringName, "amount": int, "ingredients": { StringName: int } }
static func parse_recipes(json_text: String, known_ids: Array[StringName]) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var data: Variant = JSON.parse_string(json_text)
	if typeof(data) != TYPE_DICTIONARY or typeof(data.get("recipes")) != TYPE_ARRAY:
		push_error("CraftingProcessor: recipes JSON 형식 오류")
		return out
	for raw: Variant in data["recipes"]:
		if typeof(raw) != TYPE_DICTIONARY:
			push_error("CraftingProcessor: 레시피 항목이 Dictionary가 아님")
			continue
		var id := StringName(str(raw.get("id", "")))
		var result := StringName(str(raw.get("result", "")))
		var amount := int(raw.get("amount", 0))
		var raw_ing: Variant = raw.get("ingredients", {})
		if id == &"" or amount <= 0 or not known_ids.has(result) or typeof(raw_ing) != TYPE_DICTIONARY or raw_ing.is_empty():
			push_error("CraftingProcessor: 레시피 '%s' 건너뜀 (id/결과/수량/재료 오류)" % id)
			continue
		var ingredients := {}
		var valid := true
		for key: Variant in raw_ing:
			var ing_id := StringName(str(key))
			var need := int(raw_ing[key])
			if not known_ids.has(ing_id) or need <= 0:
				push_error("CraftingProcessor: 레시피 '%s' 건너뜀 (알 수 없는 재료 '%s' 또는 수량 %d)" % [id, ing_id, need])
				valid = false
				break
			ingredients[ing_id] = need
		if valid:
			out.append({ "id": id, "result": result, "amount": amount, "ingredients": ingredients })
	return out

func configure(inv: InventoryData, recipe_list: Array[Dictionary], item_lookup: Callable) -> void:
	if inventory != null and inventory.item_added.is_connected(_on_item_added):
		inventory.item_added.disconnect(_on_item_added)
	inventory = inv
	recipes = recipe_list
	_lookup = item_lookup
	discovered.clear()
	_unlocked.clear()
	inventory.item_added.connect(_on_item_added)

func is_unlocked(recipe_id: StringName) -> bool:
	return _unlocked.has(recipe_id)

func can_craft(recipe_id: StringName) -> bool:
	var recipe := get_recipe(recipe_id)
	return not recipe.is_empty() and is_unlocked(recipe_id) and _has_ingredients(recipe)

func craft(recipe_id: StringName) -> bool:
	var recipe := get_recipe(recipe_id)
	# 1. 해금 여부
	if recipe.is_empty() or not is_unlocked(recipe_id):
		craft_failed.emit(recipe_id, &"locked")
		return false
	# 2. 전체 확인 (부족하면 아무것도 소모하지 않음)
	if not _has_ingredients(recipe):
		craft_failed.emit(recipe_id, &"missing")
		return false
	# 3. 소모
	var ingredients: Dictionary = recipe["ingredients"]
	for ing_id: StringName in ingredients:
		inventory.remove_item(ing_id, ingredients[ing_id])
	# 4. 지급 (자리가 없으면 재료를 되돌림)
	var result: ItemData = _lookup.call(recipe["result"])
	if inventory.add_item(result, recipe["amount"]) > 0:
		for ing_id: StringName in ingredients:
			inventory.add_item(_lookup.call(ing_id), ingredients[ing_id])
		craft_failed.emit(recipe_id, &"no_space")
		return false
	# 5.
	crafted.emit(recipe_id)
	return true

func get_recipe(recipe_id: StringName) -> Dictionary:
	for recipe in recipes:
		if recipe["id"] == recipe_id:
			return recipe
	return {}

func _has_ingredients(recipe: Dictionary) -> bool:
	var ingredients: Dictionary = recipe["ingredients"]
	for ing_id: StringName in ingredients:
		if not inventory.has_item(ing_id, ingredients[ing_id]):
			return false
	return true

## 새 item_id를 처음 받으면 발견으로 기록하고, 재료가 모두 발견된 레시피를 해금한다.
func _on_item_added(item: ItemData, _amount: int) -> void:
	if discovered.has(item.id):
		return
	discovered[item.id] = true
	for recipe in recipes:
		var recipe_id: StringName = recipe["id"]
		if _unlocked.has(recipe_id):
			continue
		var all_found := true
		for ing_id: StringName in recipe["ingredients"]:
			if not discovered.has(ing_id):
				all_found = false
				break
		if all_found:
			_unlocked[recipe_id] = true
			recipe_unlocked.emit(recipe_id)
