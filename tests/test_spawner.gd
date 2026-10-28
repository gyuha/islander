extends "res://tests/test_case.gd"

const PLAYER_POS := Vector3(5.0, 0.0, 5.0)

func test_never_inside_safe_radius() -> void:
	var sp := EnemySpawner.new()
	sp.land_projector = func(p: Vector3) -> Vector3: return p
	sp.rng.seed = 12345
	var found := 0
	for i in 200:
		var p := sp.find_spawn_point(PLAYER_POS)
		if p != Vector3.INF:
			found += 1
			assert_true(p.distance_to(PLAYER_POS) >= 12.0, "플레이어와 거리 %f >= 12" % p.distance_to(PLAYER_POS))
	assert_true(found > 0, "성공한 스폰이 한 번 이상")
	sp.free()

func test_bounded_retries() -> void:
	var sp := EnemySpawner.new()
	sp.land_projector = func(_p: Vector3) -> Vector3: return PLAYER_POS
	sp.rng.seed = 1
	var p := sp.find_spawn_point(PLAYER_POS)
	assert_eq(p, Vector3.INF, "항상 실패하면 INF")
	assert_eq(sp.last_attempts, sp.max_attempts, "시도 횟수 == max_attempts")
	sp.free()
