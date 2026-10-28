# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/inventory_system_inventory_data_resource.gd
# Modified for dongval: InventoryItem → ItemData, 무게 초과 시 전량 거부 → 들어갈 만큼만 추가, 스택 비교는 id, 비스택 아이템은 슬롯당 1개,
#   빈 슬롯은 새 ItemSlot으로 교체하지 않고 기존 슬롯 값을 채움, item_added 시그널·create/remove_item/has_item/count_of/get_slot 추가
class_name InventoryData extends Resource

signal inventory_updated                                  # 한 번의 변경 호출당 최대 1회
signal item_added(item: ItemData, amount: int)            # 실제로 들어간 수량(>0)일 때만

@export var slots: Array[ItemSlot] = []
@export var max_weight: float = 200.0

static func create(slot_count: int = 20) -> InventoryData:
	var inv := InventoryData.new()
	for i in slot_count:
		inv.slots.append(ItemSlot.new())
	return inv

func get_total_weight() -> float:
	var total := 0.0
	for slot in slots:
		if not slot.is_empty():
			total += slot.item.weight * float(slot.quantity)
	return total

## 무게로 들어갈 수 있는 수량까지 자른 뒤 → 기존 스택 채우기 → 빈 슬롯 순서로 넣는다.
## 반환: 들어가지 못한 수량 (0 = 전량 성공).
func add_item(new_item: ItemData, count: int = 1) -> int:
	if new_item == null or count <= 0:
		return count

	var allowed := count
	if new_item.weight > 0.0:
		var room := floori((max_weight - get_total_weight() + 0.0001) / new_item.weight)
		allowed = mini(count, maxi(room, 0))

	var remaining := allowed

	# Pass 1: 부분 스택
	if new_item.stackable:
		for slot in slots:
			if remaining <= 0:
				break
			if not slot.is_empty() and slot.item.id == new_item.id and slot.quantity < new_item.max_stack:
				var to_add := mini(new_item.max_stack - slot.quantity, remaining)
				slot.quantity += to_add
				remaining -= to_add

	# Pass 2: 빈 슬롯
	if remaining > 0:
		for slot in slots:
			if remaining <= 0:
				break
			if slot.is_empty():
				var to_add := 1
				if new_item.stackable:
					to_add = mini(remaining, new_item.max_stack)
				slot.item = new_item
				slot.quantity = to_add
				remaining -= to_add

	var added := allowed - remaining
	if added > 0:
		inventory_updated.emit()
		item_added.emit(new_item, added)
	return count - added

## 보유량이 부족하면 아무것도 빼지 않고 false. 뒤쪽 슬롯부터 뺀다.
func remove_item(item_id: StringName, count: int) -> bool:
	if count <= 0 or count_of(item_id) < count:
		return false
	var remaining := count
	for i in range(slots.size() - 1, -1, -1):
		if remaining <= 0:
			break
		var slot := slots[i]
		if slot.is_empty() or slot.item.id != item_id:
			continue
		var take := mini(slot.quantity, remaining)
		_take_from(slot, take)
		remaining -= take
	inventory_updated.emit()
	return true

## count가 -1이면 슬롯을 비운다.
func remove_at(index: int, count: int = -1) -> void:
	if index < 0 or index >= slots.size():
		return
	var slot := slots[index]
	if count < 0 or count >= slot.quantity:
		slot.item = null
		slot.quantity = 0
	else:
		slot.quantity -= count
	inventory_updated.emit()

func has_item(item_id: StringName, count: int = 1) -> bool:
	return count_of(item_id) >= count

func count_of(item_id: StringName) -> int:
	var total := 0
	for slot in slots:
		if not slot.is_empty() and slot.item.id == item_id:
			total += slot.quantity
	return total

func get_slot(index: int) -> ItemSlot:
	if index < 0 or index >= slots.size():
		return null
	return slots[index]

func _take_from(slot: ItemSlot, amount: int) -> void:
	slot.quantity -= amount
	if slot.quantity <= 0:
		slot.item = null
		slot.quantity = 0
