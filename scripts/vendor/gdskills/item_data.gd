# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/inventory_system_inventory_item_resource.gd
# Modified for dongval: InventoryItem → ItemData, id StringName, weight/consumables/tool_*/damage/reach 추가, 스택 기본값 변경, use() 삭제
class_name ItemData extends Resource

@export var id: StringName = &""
@export var name: String = ""            # 표시 이름(한글)
@export var icon: Texture2D               # res://assets/ui/icons/<id>.png (없으면 null 허용)
@export var stackable: bool = true
@export var max_stack: int = 64
@export var weight: float = 1.0
@export var consumables: Dictionary = {}  # { "hunger": 15.0 } — 비어 있지 않으면 음식
@export var tool_type: StringName = &""   # &"", &"axe", &"pickaxe", &"spear"
@export var tool_tier: int = 0
@export var damage: int = 0               # 공격 피해 (도구가 아니면 0 → 맨손 값 사용)
@export var reach: float = 0.0
@export_multiline var description: String = ""

func is_food() -> bool:
	return not consumables.is_empty()

func is_tool() -> bool:
	return tool_type != &""
