extends SceneTree
# 실행: godot --headless --path . -s tests/run_tests.gd  (종료 코드 0 = 전부 통과, 1 = 실패 있음)

func _initialize() -> void:
	var passed := 0
	var failed := 0
	var files: Array[String] = []
	for f in DirAccess.get_files_at("res://tests"):
		if f.begins_with("test_") and f.ends_with(".gd") and f != "test_case.gd":
			files.append(f)
	files.sort()
	for f in files:
		var script := load("res://tests/" + f) as GDScript
		if script == null or not script.can_instantiate():
			failed += 1
			print("FAIL %s::<load> — 스크립트를 불러오지 못함(파싱 오류)" % f)
			continue
		var suite: RefCounted = script.new()
		var methods: Array[String] = []
		for m in suite.get_method_list():
			if String(m["name"]).begins_with("test_"):
				methods.append(m["name"])
		methods.sort()
		for method in methods:
			suite.failures.clear()
			if suite.has_method("before_each"):
				suite.call("before_each")
			suite.call(method)
			if suite.failures.is_empty():
				passed += 1
				print("PASS %s::%s" % [f, method])
			else:
				failed += 1
				print("FAIL %s::%s — %s" % [f, method, "; ".join(suite.failures)])
	print("RESULT passed=%d failed=%d" % [passed, failed])
	quit(1 if failed > 0 else 0)
