extends Node
# Autoload "ItemDB" — class_name을 붙이지 않는다(싱글턴 이름과 충돌).

const ITEMS_DIR := "res://data/items"
const RECIPES_PATH := "res://data/recipes.json"

var items: Dictionary = {}               # StringName → ItemData
var recipes: Array[Dictionary] = []      # CraftingProcessor.parse_recipes 결과

func _ready() -> void:
	for file in DirAccess.get_files_at(ITEMS_DIR):
		var file_name := file.trim_suffix(".remap")   # 내보내기 빌드의 .remap 접미사
		if not file_name.ends_with(".tres"):
			continue
		var item := load(ITEMS_DIR.path_join(file_name)) as ItemData
		if item == null or item.id == &"":
			push_error("ItemDB: 아이템 로드 실패 또는 id 없음: %s" % file_name)
			continue
		items[item.id] = item
	var known_ids: Array[StringName] = []
	known_ids.assign(items.keys())
	recipes = CraftingProcessor.parse_recipes(FileAccess.get_file_as_string(RECIPES_PATH), known_ids)

func get_item(id: StringName) -> ItemData:
	if not items.has(id):
		push_error("ItemDB: 알 수 없는 아이템 id '%s'" % id)
		return null
	return items[id]
