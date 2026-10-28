extends "res://tests/test_case.gd"

## receive_item만 흉내 내는 사용자. capacity개까지만 받고 나머지는 돌려준다.
class FakeUser extends Node:
	var capacity: int = 0
	var received: int = 0
	func receive_item(_id: StringName, amount: int) -> int:
		var take := mini(amount, capacity)
		capacity -= take
		received += take
		return amount - take

var harvested_total: int = 0

func _on_harvested(_id: StringName, amount: int) -> void:
	harvested_total += amount

func _tree() -> Harvestable:
	var h := Harvestable.new()
	h.hp = h.max_hp
	harvested_total = 0
	h.harvested.connect(_on_harvested)
	return h

func test_hit_full_inventory_does_nothing() -> void:
	var h := _tree()
	var u := FakeUser.new()
	h.hit(u, &"", 0)
	assert_eq(h.hp, 6, "가방이 가득이면 노드 피해 없음")
	assert_eq(u.received, 0, "받은 수량 0")
	assert_eq(harvested_total, 0, "harvested 시그널 없음")
	assert_true(h.can_interact(), "고갈되지 않음")
	h.free()
	u.free()

func test_hit_partial_gives_what_fits_without_damage() -> void:
	var h := _tree()
	var u := FakeUser.new()
	u.capacity = 2
	h.hit(u, &"axe", 1)            # 도끼 등급1 → 수확량 3, 2개만 들어감
	assert_eq(u.received, 2, "들어간 만큼만 받음")
	assert_eq(harvested_total, 2, "harvested는 실제 지급량")
	assert_eq(h.hp, 6, "일부만 들어가면 노드 피해 없음")
	h.free()
	u.free()

func test_hit_fits_damages_node() -> void:
	var h := _tree()
	var u := FakeUser.new()
	u.capacity = 10
	h.hit(u, &"axe", 1)
	assert_eq(u.received, 3, "도끼 수확량 3")
	assert_eq(h.hp, 4, "선호 도구 피해 2")
	h.free()
	u.free()

func test_berry_full_inventory_not_depleted() -> void:
	var b := _tree()
	b.harvest_by_hit = false
	var u := FakeUser.new()
	b.interact(u)
	assert_eq(u.received, 0, "하나도 못 받음")
	assert_true(b.can_interact(), "덤불은 고갈되지 않음")
	assert_true(b.usable_with_key(), "E로 계속 쓸 수 있음")
	b.free()
	u.free()

func test_berry_partial_keeps_remainder() -> void:
	var b := _tree()
	b.harvest_by_hit = false
	var u := FakeUser.new()
	u.capacity = 1
	b.interact(u)                  # 3개 중 1개만
	assert_eq(u.received, 1, "1개 받음")
	assert_true(b.can_interact(), "아직 고갈 아님")
	u.capacity = 1
	b.interact(u)                  # 남은 2개 중 1개
	assert_eq(u.received, 2, "누적 2개")
	assert_true(b.can_interact(), "남은 1개가 있어 고갈 아님")
	b.free()
	u.free()

func test_hit_type_not_usable_with_key() -> void:
	var t := _tree()
	assert_true(t.can_interact(), "타격형도 can_interact")
	assert_true(not t.usable_with_key(), "타격형은 E 대상이 아님")
	t.free()
