class_name IslandLayout extends RefCounted
# 섬 레이아웃(순수 데이터 + 질의). 노드·씬·전역 RNG 접근 금지. 워커 스레드에서 만들고 이후 읽기 전용.
# 설계: docs/architecture/world-island.md (IslandLayout 절)

const SEA_FLOOR := -2.0
const BEACH_TOP := 0.40                       # 1단 벽 발치의 모래 높이
const LEVEL_HEIGHT: Array[float] = [0.40, 1.20, 2.10, 2.90]   # [level] 캡 높이. 0 = 해변 꼭대기
const LIP_INSET := 0.20
const RAMP_WIDTH := 3.0
const RAMP_LENGTH := 2.4
const RAMP_SIDE_SLOPE_DEG := 30.0

# [중심각(°), amp, 반폭 w(°)]  (docs: 본섬과 1단 표)
const LOBES: Array[Array] = [
	[10.0, 0.28, 34.0], [90.0, 0.14, 36.0], [150.0, -0.26, 26.0],
	[205.0, 0.26, 34.0], [270.0, 0.12, 40.0], [325.0, -0.22, 22.0],
]
const RAMP_COUNTS: Array[int] = [4, 1, 2, 2, 1, 1]       # 고원 순서(본섬, 작은 섬, 2단 a·b·c, 3단)

class Plateau extends RefCounted:
	var level: int = 1                        # 1~3
	var parent: int = -1                      # plateaus 인덱스. 1단은 -1
	var center: Vector2 = Vector2.ZERO        # (x, z)
	var radii: PackedFloat32Array             # radii[i] = 각도 i·TAU/N 방향 반지름 (각도 = atan2(z, x))
	var beach: PackedFloat32Array             # 1단만: 같은 각도의 해변 폭 B. 그 외 빈 배열
	var outline: PackedVector2Array           # center + radii[i]·(cos, sin)
	var normals: PackedVector2Array           # 바깥 단위 법선
	var max_radius: float = 0.0

	## radii로부터 outline·normals·max_radius를 다시 계산한다.
	func finalize() -> void:
		var n := radii.size()
		outline.resize(n)
		normals.resize(n)
		max_radius = 0.0
		for i in n:
			var th := float(i) * TAU / float(n)
			outline[i] = center + radii[i] * Vector2(cos(th), sin(th))
			max_radius = maxf(max_radius, radii[i])
		for i in n:
			var d := outline[(i + 1) % n] - outline[(i - 1 + n) % n]
			normals[i] = Vector2(d.y, -d.x).normalized()

	func _angle_index(x: float, z: float) -> Vector2:
		# (정수부 인덱스, 소수부)를 Vector2로. θ = atan2(dz, dx) in [0, TAU)
		var th := atan2(z - center.y, x - center.x)
		if th < 0.0:
			th += TAU
		var f := th / TAU * float(radii.size())
		var i0 := int(f)
		return Vector2(float(i0), f - float(i0))

	func radius_at_angle(theta: float) -> float:
		var th := fposmod(theta, TAU)
		var n := radii.size()
		var f := th / TAU * float(n)
		var i0 := int(f) % n
		return lerpf(radii[i0], radii[(i0 + 1) % n], f - floorf(f))

	## ρ − r(θ). 음수 = 안.
	func radial_offset(x: float, z: float) -> float:
		var ai := _angle_index(x, z)
		var n := radii.size()
		var i0 := int(ai.x) % n
		var r := lerpf(radii[i0], radii[(i0 + 1) % n], ai.y)
		return Vector2(x - center.x, z - center.y).length() - r

	func beach_width(x: float, z: float) -> float:
		if beach.is_empty():
			return 0.0
		var ai := _angle_index(x, z)
		var n := beach.size()
		var i0 := int(ai.x) % n
		return lerpf(beach[i0], beach[(i0 + 1) % n], ai.y)

	## 경계원 밖(여유 포함)이면 계산을 건너뛰고 하한값을 돌려준다.
	func offset_fast(x: float, z: float, margin: float) -> float:
		var rho := Vector2(x - center.x, z - center.y).length()
		if rho > max_radius + margin:
			return rho - max_radius
		return radial_offset(x, z)

class Ramp extends RefCounted:
	var plateau: int = 0
	var origin: Vector2 = Vector2.ZERO        # 벽선 위 입구 중심
	var dir: Vector2 = Vector2.RIGHT          # 바깥 법선 n (단위)
	var h_top: float = 0.0
	var h_foot: float = 0.0

	func side_run() -> float:
		return (h_top - h_foot) / tan(deg_to_rad(IslandLayout.RAMP_SIDE_SLOPE_DEG))

	func half_extent() -> float:
		return IslandLayout.RAMP_WIDTH * 0.5 + side_run()

	## (s, t): s = (p−origin)·n, t = (p−origin)·(−n.y, n.x)
	func local(x: float, z: float) -> Vector2:
		var d := Vector2(x, z) - origin
		return Vector2(d.dot(dir), d.dot(Vector2(-dir.y, dir.x)))

	## 발자국 밖이면 -INF
	func height_at(x: float, z: float) -> float:
		var st := local(x, z)
		var s := st.x
		var t := absf(st.y)
		if s < -1.0 or s > IslandLayout.RAMP_LENGTH or t > half_extent():
			return -INF
		var axis := lerpf(h_top, h_foot, s / IslandLayout.RAMP_LENGTH) if s >= 0.0 else h_top - 0.03
		return axis - maxf(0.0, t - IslandLayout.RAMP_WIDTH * 0.5) * tan(deg_to_rad(IslandLayout.RAMP_SIDE_SLOPE_DEG))

	func in_footprint(x: float, z: float, margin: float) -> bool:
		var st := local(x, z)
		return st.x >= -1.0 - margin and st.x <= IslandLayout.RAMP_LENGTH + margin and absf(st.y) <= half_extent() + margin

	func in_mouth(x: float, z: float) -> bool:
		var st := local(x, z)
		return st.x >= -1.0 and st.x <= 0.75 and absf(st.y) <= IslandLayout.RAMP_WIDTH * 0.5 - 0.2

var plateaus: Array[Plateau] = []
var ramps: Array[Ramp] = []
var spit_a: Vector2 = Vector2.ZERO            # 모래톱 선분 양 끝
var spit_b: Vector2 = Vector2.ZERO

# ---------------------------------------------------------------- 질의

## 모래·해저만(고원·경사로 제외). 바닥 격자 메시용.
func base_height(x: float, z: float) -> float:
	var h := SEA_FLOOR
	h = maxf(h, _sand_for(plateaus[0], x, z, -1.0))
	h = maxf(h, _sand_for(plateaus[1], x, z, 2.3))
	h = maxf(h, _sand(_seg_dist(x, z, spit_a, spit_b) - 1.0, 0.20, 1.5))
	return h

## 고원·모래 단면(경사로 제외)
func _ground_height(x: float, z: float) -> float:
	var h := base_height(x, z)
	for p in plateaus:
		if Vector2(x - p.center.x, z - p.center.y).length_squared() > p.max_radius * p.max_radius:
			continue
		if p.radial_offset(x, z) < 0.0:
			h = maxf(h, LEVEL_HEIGHT[p.level])
	return h

## 지면 높이(고원 캡 포함, 경사로 제외). 경사로 둔덕 메시가 쓴다.
func ground_height(x: float, z: float) -> float:
	return _ground_height(x, z)

## max(base_height, 포함하는 고원 캡 높이, 경사로 height_at)
func height_at(x: float, z: float) -> float:
	var h := _ground_height(x, z)
	for r in ramps:
		if (Vector2(x, z) - r.origin).length_squared() > 64.0:
			continue
		h = maxf(h, r.height_at(x, z))
	return h

## 점을 포함하는 고원 중 최대 level, 없으면 0 (경사로 무시)
func level_at(x: float, z: float) -> int:
	var lv := 0
	for p in plateaus:
		if p.level <= lv:
			continue
		if Vector2(x - p.center.x, z - p.center.y).length_squared() > p.max_radius * p.max_radius:
			continue
		if p.radial_offset(x, z) < 0.0:
			lv = p.level
	return lv

## 모든 고원의 |radial_offset| 최솟값 (반지름 방향 근사)
func wall_distance(x: float, z: float) -> float:
	var d := INF
	for p in plateaus:
		d = minf(d, absf(p.offset_fast(x, z, 8.0)))
	return d

func in_any_ramp(x: float, z: float, margin: float) -> bool:
	for r in ramps:
		if (Vector2(x, z) - r.origin).length_squared() > 100.0:
			continue
		if r.in_footprint(x, z, margin):
			return true
	return false

func sample_heights(resolution: int, cell_size: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(resolution * resolution)
	var half := (resolution - 1) * cell_size * 0.5
	for j in resolution:
		var z := j * cell_size - half
		for i in resolution:
			out[j * resolution + i] = height_at(i * cell_size - half, z)
	return out

func sample_levels(resolution: int, cell_size: float) -> PackedByteArray:
	var out := PackedByteArray()
	out.resize(resolution * resolution)
	var half := (resolution - 1) * cell_size * 0.5
	for j in resolution:
		var z := j * cell_size - half
		for i in resolution:
			out[j * resolution + i] = level_at(i * cell_size - half, z)
	return out

func sample_base(resolution: int, cell_size: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(resolution * resolution)
	var half := (resolution - 1) * cell_size * 0.5
	for j in resolution:
		var z := j * cell_size - half
		for i in resolution:
			out[j * resolution + i] = base_height(i * cell_size - half, z)
	return out

# ---------------------------------------------------------------- 단면 헬퍼

## u ≤ 0 → top, 0 < u ≤ width → 마른 모래(선형), 그 너머 → 물속 단면(−2.0까지)
static func _sand(u: float, top: float, width: float) -> float:
	if u <= 0.0:
		return top
	if u <= width:
		return top * (1.0 - u / width)
	var v := u - width
	if v >= 7.0:
		return SEA_FLOOR
	if v <= 0.8:
		return lerpf(0.0, -0.40, v / 0.8)
	if v <= 4.0:
		return lerpf(-0.40, -0.80, (v - 0.8) / 3.2)
	return lerpf(-0.80, SEA_FLOOR, (v - 4.0) / 3.0)

func _sand_for(p: Plateau, x: float, z: float, fixed_width: float) -> float:
	var rho := Vector2(x - p.center.x, z - p.center.y).length()
	if rho > p.max_radius + 16.0:
		return SEA_FLOOR
	var u := p.radial_offset(x, z)
	var width := fixed_width if fixed_width > 0.0 else p.beach_width(x, z)
	return _sand(u, BEACH_TOP, width)

static func _seg_dist(x: float, z: float, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var t := clampf(((x - a.x) * ab.x + (z - a.y) * ab.y) / ab.length_squared(), 0.0, 1.0)
	return Vector2(x, z).distance_to(a + ab * t)

# ---------------------------------------------------------------- 생성

static func _bump(delta: float, w: float) -> float:
	return 0.5 * (1.0 + cos(PI * clampf(delta / w, -1.0, 1.0)))

static func _wrap_pi(a: float) -> float:
	return fposmod(a + PI, TAU) - PI

## 각도 노이즈 n_k(θ): 반지름 15 m 원 위를 샘플해 주기성이 있다.
static func _n(noise: IslandNoise, theta: float, k: int) -> float:
	return noise.sample(15.0 * cos(theta) + 200.0 * float(k), 15.0 * sin(theta))

static func _sample_count(r_nominal: float) -> int:
	return clampi(int(TAU * r_nominal / 0.35), 64, 512)

@warning_ignore("shadowed_global_identifier")
static func build(seed: int, radius: float) -> IslandLayout:
	var lay := IslandLayout.new()
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var noise := IslandNoise.new()
	noise.configure(seed, 0.04)

	# 1. 로브 지터
	var lobes: Array[Vector3] = []             # (각도 rad, amp, 반폭 rad)
	for l in LOBES:
		var a := deg_to_rad(float(l[0]) + rng.randf_range(-6.0, 6.0))
		var amp := float(l[1]) * rng.randf_range(0.85, 1.15)
		lobes.append(Vector3(a, amp, deg_to_rad(float(l[2]))))

	# 2. 본섬 1단
	var main := Plateau.new()
	main.level = 1
	var n_main := _sample_count(radius)
	main.radii.resize(n_main)
	main.beach.resize(n_main)
	for i in n_main:
		var th := float(i) * TAU / float(n_main)
		var s := 1.0
		for lb in lobes:
			s += lb.y * _bump(_wrap_pi(th - lb.x), lb.z)
		var r_l := radius * s * (1.0 + 0.04 * _n(noise, th, 0))
		var b := 5.0 + 1.2 * _n(noise, th, 1)
		main.beach[i] = b
		main.radii[i] = r_l - b
	main.finalize()
	lay.plateaus.append(main)

	# 작은 섬 1단
	var isl := Plateau.new()
	isl.level = 1
	var isl_dir := Vector2(cos(lobes[2].x), sin(lobes[2].x))
	isl.center = isl_dir * 31.5
	var n_isl := _sample_count(7.0)
	isl.radii.resize(n_isl)
	isl.beach.resize(n_isl)
	for i in n_isl:
		var th := float(i) * TAU / float(n_isl)
		isl.beach[i] = 2.3
		isl.radii[i] = 7.0 * (1.0 + 0.08 * _n(noise, th, 2)) - 2.3
	isl.finalize()
	lay.plateaus.append(isl)

	# 모래톱
	var th_dir := isl_dir.angle()
	lay.spit_a = isl_dir * (main.radius_at_angle(th_dir) + 1.0)
	lay.spit_b = isl.center - isl_dir * (isl.radius_at_angle(th_dir + PI) + 1.0)

	# 2단 a·b·c, 3단
	var tiers: Array[Array] = [
		[deg_to_rad(15.0), 16.0, 10.5, 0, 3, 2],      # [각도, 거리, R, 부모 인덱스, 노이즈 채널 k, level]
		[deg_to_rad(210.0), 16.5, 10.5, 0, 4, 2],
		[deg_to_rad(100.0), 17.0, 8.5, 0, 5, 2],
	]
	for t in tiers:
		var c := Vector2(cos(float(t[0])), sin(float(t[0]))) * float(t[1])
		lay.plateaus.append(_make_tier(lay, noise, rng, c, float(t[2]), int(t[3]), int(t[4]), int(t[5])))
	var t2a := lay.plateaus[2]
	lay.plateaus.append(_make_tier(lay, noise, rng, t2a.center, 4.5, 2, 6, 3))

	# 4. 경사로
	lay._choose_ramps(rng)
	return lay

static func _make_tier(lay: IslandLayout, noise: IslandNoise, rng: RandomNumberGenerator, c: Vector2, r_nom: float, parent: int, k: int, level: int) -> Plateau:
	var p := Plateau.new()
	p.level = level
	p.parent = parent
	p.center = c
	var phi := rng.randf() * TAU
	var n := _sample_count(r_nom)
	p.radii.resize(n)
	for i in n:
		var th := float(i) * TAU / float(n)
		p.radii[i] = r_nom * (1.0 + 0.10 * sin(2.0 * th + phi) + 0.05 * _n(noise, th, k))
	p.finalize()
	var par := lay.plateaus[parent]
	_clamp_inside(p, par, 3.5)
	for _pass in 3:
		_smooth(p)
	_clamp_inside(p, par, 3.0)
	# 같은 단 고원끼리 윤곽 간격 ≥ 3 m(테스트 불변식)을 노이즈와 무관하게 보장한다. 이미 충분히 떨어져 있으면 아무 일도 하지 않는다.
	for other in lay.plateaus:
		if other.level == level:
			_clamp_apart(p, other, 3.8)
			for _pass in 6:
				_smooth(p)
			_clamp_apart(p, other, 3.4)
			for _pass in 2:
				_smooth(p)
	_clamp_inside(p, par, 3.0)
	return p

## other 바깥으로 gap보다 가까운 정점의 반지름을 줄인다(4회 반복). 반경 방향 근사라 여유를 둔다.
static func _clamp_apart(p: Plateau, other: Plateau, gap: float) -> void:
	for _iter in 4:
		for i in p.radii.size():
			var o := p.outline[i]
			var u := other.radial_offset(o.x, o.y)
			if u < gap:
				p.radii[i] -= gap - u
		p.finalize()

## 각 정점의 부모 안쪽 여유가 ledge보다 작으면 반지름을 줄인다(4회 반복).
static func _clamp_inside(p: Plateau, parent: Plateau, ledge: float) -> void:
	var n := p.radii.size()
	for _iter in 4:
		for i in n:
			var o := p.outline[i]
			var u := parent.radial_offset(o.x, o.y)
			if u > -ledge:
				p.radii[i] -= u + ledge
		p.finalize()

static func _smooth(p: Plateau) -> void:
	var n := p.radii.size()
	var out := PackedFloat32Array()
	out.resize(n)
	for i in n:
		out[i] = 0.25 * p.radii[(i - 1 + n) % n] + 0.5 * p.radii[i] + 0.25 * p.radii[(i + 1) % n]
	p.radii = out
	p.finalize()

# ---------------------------------------------------------------- 경사로 선택

func _choose_ramps(rng: RandomNumberGenerator) -> void:
	var tan_side := tan(deg_to_rad(RAMP_SIDE_SLOPE_DEG))
	for pi in plateaus.size():
		var p := plateaus[pi]
		var count := RAMP_COUNTS[pi]
		var parent_level := p.level - 1
		var h_top := LEVEL_HEIGHT[p.level]
		var n := p.outline.size()
		# 후보: 윤곽 샘플 10° 간격(36개)
		var cands: Array[Ramp] = []
		var cand_angle: Array[float] = []
		for k in 36:
			var i := k * n / 36
			var origin := p.outline[i]
			var nrm := p.normals[i]
			var tang := Vector2(-nrm.y, nrm.x)
			var foot := origin + nrm * RAMP_LENGTH
			var foot2 := origin + nrm * (RAMP_LENGTH + 1.0)
			if level_at(foot.x, foot.y) != parent_level or level_at(foot2.x, foot2.y) != parent_level:
				continue
			var h_foot := LEVEL_HEIGHT[parent_level]
			if p.level == 1:
				h_foot = base_height(foot.x, foot.y)
				if h_foot < 0.12 or base_height(foot2.x, foot2.y) <= 0.05:
					continue
			var ext := RAMP_WIDTH * 0.5 + (h_top - h_foot) / tan_side
			var ok := true
			for c in [origin + tang * ext, origin - tang * ext, foot + tang * ext, foot - tang * ext]:
				var q: Vector2 = c + nrm * 0.3
				if level_at(q.x, q.y) != parent_level:
					ok = false
					break
			if not ok:
				continue
			var r := Ramp.new()
			r.plateau = pi
			r.origin = origin
			r.dir = nrm
			r.h_top = h_top
			r.h_foot = h_foot
			cands.append(r)
			cand_angle.append(float(i) * TAU / float(n))
		# 이미 고른 경사로와 6 m 이상 (origin·발치)
		var phi0 := rng.randf() * TAU
		var chosen: Array[Ramp] = []
		var chosen_angle: Array[float] = []
		for k in count:
			var pref := phi0 + float(k) * TAU / float(count)
			var best := -1
			var best_diff := INF
			for ci in cands.size():
				var diff := absf(_wrap_pi(cand_angle[ci] - pref))
				if diff >= best_diff:
					continue
				var c := cands[ci]
				var good := true
				for ca in chosen_angle:
					if absf(_wrap_pi(cand_angle[ci] - ca)) < 0.5 * TAU / float(count):
						good = false
						break
				if good and _ramp_too_close(c):
					good = false
				if good:
					best = ci
					best_diff = diff
			if best < 0:
				push_warning("IslandLayout: 고원 %d의 경사로 %d/%d개만 찾음" % [pi, k, count])
				break
			ramps.append(cands[best])
			chosen.append(cands[best])
			chosen_angle.append(cand_angle[best])

func _ramp_too_close(c: Ramp) -> bool:
	var cf := c.origin + c.dir * RAMP_LENGTH
	for r in ramps:
		var rf := r.origin + r.dir * RAMP_LENGTH
		if minf(minf(c.origin.distance_to(r.origin), c.origin.distance_to(rf)), minf(cf.distance_to(r.origin), cf.distance_to(rf))) < 6.0:
			return true
	return false
