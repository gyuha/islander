# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/inventory_system_item_slot_data.gd
# Modified for dongval: signal changed 재선언 삭제(Resource.changed + emit_changed), item 타입 ItemData, quantity 기본 0, is_empty() 추가
class_name ItemSlot extends Resource

@export var item: ItemData:
	set(val):
		item = val
		emit_changed()

@export var quantity: int = 0:
	set(val):
		quantity = val
		emit_changed()

func is_empty() -> bool:
	return item == null or quantity <= 0
