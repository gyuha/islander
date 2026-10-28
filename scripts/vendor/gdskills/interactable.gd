# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/genre_survival_interactable.gd
# Modified for dongval: print 삭제, 타입 지정, can_interact()·usable_with_key() 추가
class_name Interactable extends Area3D

@export var prompt_message: String = "상호작용"
@export var one_shot: bool = false

func interact(user: Node) -> void:
	_on_interact(user)
	if one_shot:
		queue_free()

func can_interact() -> bool:
	return true

## E 키로 쓸 수 있는가(기본: can_interact와 같다). 하위 클래스가 LMB 전용 대상을 제외한다.
func usable_with_key() -> bool:
	return can_interact()

## 하위 클래스가 재정의한다.
func _on_interact(_user: Node) -> void:
	pass
