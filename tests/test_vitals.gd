extends "res://tests/test_case.gd"

var died_count: int = 0

func _on_died() -> void:
	died_count += 1

func test_sprint_drains_three_times_walk() -> void:
	var a := Vitals.new()
	a.activity = Vitals.Activity.WALK
	a.tick(1.0)
	var walk_drain := a.max_hunger - a.hunger
	var b := Vitals.new()
	b.activity = Vitals.Activity.SPRINT
	b.tick(1.0)
	var sprint_drain := b.max_hunger - b.hunger
	assert_near(sprint_drain, walk_drain * 3.0, 0.0001, "달리기 감소량 = 걷기 × 3")
	a.free()
	b.free()

func test_starving_drains_health_gradually() -> void:
	var v := Vitals.new()
	died_count = 0
	v.died.connect(_on_died)
	v.hunger = 0.0
	v.tick(1.0)
	assert_near(v.health, 99.0, 0.0001, "1초 후 체력 (즉사 아님)")
	assert_true(not v.is_dead, "아직 생존")
	for i in 99:
		v.tick(1.0)
	assert_eq(died_count, 1, "100초 후 died 1회")
	v.tick(1.0)
	assert_eq(died_count, 1, "사망 후 추가 발생 없음")
	v.free()

func test_eat_restores_hunger() -> void:
	var v := Vitals.new()
	v.hunger = 50.0
	v.eat({ "hunger": 15.0 })
	assert_near(v.hunger, 65.0, 0.0001, "50 + 15")
	v.eat({ "hunger": 100.0 })
	assert_near(v.hunger, 100.0, 0.0001, "상한 100")
	v.free()
