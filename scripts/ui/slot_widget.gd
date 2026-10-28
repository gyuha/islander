class_name SlotWidget extends PanelContainer
# 아이콘 + 수량 슬롯. 인벤토리·제작 패널·장착 표시가 함께 쓴다. 설계: docs/architecture/worldclock-ui.md

signal clicked(index: int)

const BORDER_NORMAL := Color("#BE946D")
const BORDER_HIGHLIGHT := Color("#E0573A")

@export var index: int = -1

var _style: StyleBoxFlat

@onready var _icon: TextureRect = $Content/Icon
@onready var _letter: Label = $Content/Letter
@onready var _count: Label = $Content/Count

func _ready() -> void:
	_style = get_theme_stylebox("panel").duplicate() as StyleBoxFlat     # 인스턴스끼리 스타일 공유 방지
	add_theme_stylebox_override("panel", _style)
	set_slot(null, 0)

## item이 null이면 빈 칸, 수량 1 이하면 숫자 숨김. 아이콘이 없으면 이름 첫 글자.
func set_slot(item: ItemData, quantity: int) -> void:
	if item == null:
		_icon.texture = null
		_letter.text = ""
		_count.text = ""
		return
	_icon.texture = item.icon
	_letter.text = item.name.left(1) if item.icon == null else ""
	_count.text = str(quantity) if quantity > 1 else ""

func set_highlight(on: bool) -> void:
	_style.border_color = BORDER_HIGHLIGHT if on else BORDER_NORMAL

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		clicked.emit(index)
