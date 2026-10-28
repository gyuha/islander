extends "res://tests/test_case.gd"

var inv: InventoryData
var proc: CraftingProcessor
var items: Dictionary = {}
var unlocked_ids: Array[StringName] = []
var fail_reasons: Array[StringName] = []

func before_each() -> void:
	for id in ["wood", "stone", "berry", "stone_axe", "stone_pickaxe", "wooden_spear"]:
		items[StringName(id)] = load("res://data/items/%s.tres" % id)
	var known_ids: Array[StringName] = []
	known_ids.assign(items.keys())
	var recipes := CraftingProcessor.parse_recipes(FileAccess.get_file_as_string("res://data/recipes.json"), known_ids)
	inv = InventoryData.create(20)
	proc = CraftingProcessor.new()
	proc.configure(inv, recipes, _lookup)
	unlocked_ids.clear()
	fail_reasons.clear()
	proc.recipe_unlocked.connect(_on_unlocked)
	proc.craft_failed.connect(_on_failed)

# 테스트가 만든 Node는 메서드 끝에서 해제한다(헤드리스 종료 시 누수 경고 방지).
func _finish() -> void:
	proc.free()

func _lookup(id: StringName) -> ItemData:
	return items.get(id)

func _on_unlocked(recipe_id: StringName) -> void:
	unlocked_ids.append(recipe_id)

func _on_failed(_recipe_id: StringName, reason: StringName) -> void:
	fail_reasons.append(reason)

func test_missing_ingredients_consumes_nothing() -> void:
	inv.add_item(items[&"wood"], 3)
	inv.add_item(items[&"stone"], 1)
	assert_true(proc.is_unlocked(&"stone_axe"), "도끼 해금 상태")
	assert_true(not proc.craft(&"stone_axe"), "제작 실패")
	assert_eq(inv.count_of(&"wood"), 3, "나무 유지")
	assert_eq(inv.count_of(&"stone"), 1, "돌 유지")
	assert_eq(fail_reasons, [&"missing"] as Array[StringName], "실패 사유")
	_finish()

func test_success_consumes_exact() -> void:
	inv.add_item(items[&"wood"], 5)
	inv.add_item(items[&"stone"], 4)
	assert_true(proc.craft(&"stone_axe"), "제작 성공")
	assert_eq(inv.count_of(&"wood"), 2, "나무")
	assert_eq(inv.count_of(&"stone"), 2, "돌")
	assert_eq(inv.count_of(&"stone_axe"), 1, "도끼")
	_finish()

func test_discovery_unlocks() -> void:
	assert_true(not proc.is_unlocked(&"wooden_spear"), "처음엔 창 잠김")
	inv.add_item(items[&"wood"], 1)
	assert_eq(unlocked_ids, [&"wooden_spear"] as Array[StringName], "recipe_unlocked 1회(창)")
	assert_true(proc.is_unlocked(&"wooden_spear"), "창 해금")
	assert_true(not proc.is_unlocked(&"stone_axe"), "도끼는 아직 잠김")
	_finish()

func test_parse_rejects_unknown_item() -> void:
	# 이 테스트는 push_error 출력("알 수 없는 재료 'mystery'")을 일부러 발생시킨다.
	_finish()
	var known_ids: Array[StringName] = [&"wood", &"stone_axe"]
	var json := '{"recipes":[{"id":"ok","result":"stone_axe","amount":1,"ingredients":{"wood":3}},{"id":"bad","result":"stone_axe","amount":1,"ingredients":{"mystery":1}}]}'
	var parsed := CraftingProcessor.parse_recipes(json, known_ids)
	assert_eq(parsed.size(), 1, "유효한 레시피 수")
	assert_eq(parsed[0]["id"], &"ok", "남은 레시피")

func test_tool_tier_yield() -> void:
	assert_eq(Harvestable.calc_yield(1, &"axe", 1, &"axe"), 3, "선호 도구 등급1 = 3")
	assert_eq(Harvestable.calc_yield(1, &"", 0, &"axe"), 1, "맨손 = 1")
	assert_eq(Harvestable.calc_yield(1, &"pickaxe", 1, &"axe"), 1, "다른 도구 = 1")
	assert_eq(Harvestable.calc_node_damage(&"axe", 1, &"axe"), 2, "선호 도구 노드 피해 2")
	assert_eq(Harvestable.calc_node_damage(&"", 0, &"axe"), 1, "맨손 노드 피해 1")
	_finish()
