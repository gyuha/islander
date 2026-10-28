extends "res://tests/test_case.gd"

var inv: InventoryData
var _updated_count: int = 0

func before_each() -> void:
	inv = InventoryData.create(20)
	_updated_count = 0

func _item(id: String) -> ItemData:
	return load("res://data/items/%s.tres" % id)

func _count_updated() -> void:
	_updated_count += 1

func test_stack_overflow_splits() -> void:
	var left := inv.add_item(_item("wood"), 70)
	assert_eq(left, 0, "반환 수량")
	assert_eq(inv.get_slot(0).quantity, 64, "슬롯0")
	assert_eq(inv.get_slot(1).quantity, 6, "슬롯1")

func test_full_inventory_returns_remainder() -> void:
	var axe := _item("stone_axe")
	for i in 20:
		inv.add_item(axe, 1)
	var before := inv.get_total_weight()
	var left := inv.add_item(_item("wood"), 5)
	assert_eq(left, 5, "반환 수량")
	assert_eq(inv.count_of(&"wood"), 0, "나무 변화 없음")
	assert_near(inv.get_total_weight(), before, 0.0001, "무게 변화 없음")

func test_weight_limit_partial() -> void:
	inv.max_weight = 10.0
	var left := inv.add_item(_item("stone"), 8)
	assert_eq(inv.count_of(&"stone"), 5, "들어간 수량")
	assert_eq(left, 3, "반환 수량")

func test_remove_item() -> void:
	inv.add_item(_item("wood"), 10)
	assert_true(inv.remove_item(&"wood", 4), "4개 제거 성공")
	assert_eq(inv.count_of(&"wood"), 6, "제거 후 수량")
	assert_true(not inv.remove_item(&"wood", 7), "7개 제거 실패")
	assert_eq(inv.count_of(&"wood"), 6, "실패 시 수량 유지")

func test_single_signal_per_call() -> void:
	inv.inventory_updated.connect(_count_updated)
	inv.add_item(_item("wood"), 130)
	assert_eq(_updated_count, 1, "inventory_updated 횟수")
