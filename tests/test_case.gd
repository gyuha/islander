extends RefCounted
# 테스트 기반 클래스. class_name 없음 — 테스트 파일은 extends "res://tests/test_case.gd".

var failures: Array[String] = []

func assert_true(cond: bool, msg: String) -> void:
	if not cond:
		failures.append(msg)

func assert_eq(a: Variant, b: Variant, msg: String) -> void:
	if a != b:
		failures.append("%s (기대 %s, 실제 %s)" % [msg, str(b), str(a)])

func assert_near(a: float, b: float, eps: float, msg: String) -> void:
	if absf(a - b) > eps:
		failures.append("%s (기대 %s ± %s, 실제 %s)" % [msg, str(b), str(eps), str(a)])
