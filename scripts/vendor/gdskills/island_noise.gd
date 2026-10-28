# Origin: GDSkills / gd-agentic-skills (LGPL-3.0) — .claude/skills/godot-master/scripts/procedural_generation_fast_noise_noise2d_master.gd
# Modified for dongval: extends Node → RefCounted + class_name IslandNoise, 노이즈 SIMPLEX_SMOOTH/FBM/옥타브 3, sample(x, z) 추가.
#   스레드마다 새 인스턴스를 만들어 쓴다(공유 금지).
class_name IslandNoise extends RefCounted

var noise := FastNoiseLite.new()
var rng := RandomNumberGenerator.new()

@warning_ignore("shadowed_global_identifier")
func configure(seed: int, frequency: float = 0.01) -> void:
	rng.seed = seed
	noise.seed = seed
	noise.frequency = frequency
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	noise.fractal_octaves = 3

func generate_heightmap(width: int, height: int) -> Image:
	return noise.get_image(width, height)

## 월드 좌표(x, z)의 노이즈 값, -1..1.
func sample(x: float, z: float) -> float:
	return noise.get_noise_2d(x, z)
