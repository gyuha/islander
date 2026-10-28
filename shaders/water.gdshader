// 물: 단색 평면 + 수심 그라데이션 + 해안 거품 띠 + 노멀 2장 스크롤. 정점 파도 없음.
// 설계: docs/art/style-guide.md 6절, docs/architecture/world-island.md 물 절. 깊이 텍스처를 읽으므로 투명 패스로 그려진다.
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform vec4 shallow_color : source_color = vec4(0.498, 0.827, 0.769, 1.0);   // #7FD3C4
uniform vec4 deep_color : source_color = vec4(0.278, 0.651, 0.576, 1.0);      // #47A693
uniform vec4 foam_color : source_color = vec4(0.918, 0.973, 0.953, 1.0);      // #EAF8F3
uniform float depth_fade = 1.2;       // 불변식: depth_fade ≤ |SEA_FLOOR| − 0.5 (SEA_FLOOR = −2.0)
uniform float foam_width = 0.35;
uniform float foam_wobble = 0.05;       // 거품 가장자리 일렁임 (m)
uniform float scroll_speed = 0.02;
uniform float uv_scale = 0.06;          // 월드 m → UV
uniform float normal_depth = 0.5;
uniform sampler2D normal_a : hint_normal, repeat_enable, filter_linear;
uniform sampler2D normal_b : hint_normal, repeat_enable, filter_linear;
uniform sampler2D depth_tex : hint_depth_texture, repeat_disable, filter_nearest;

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	// 수면에서 그 뒤 지오메트리까지의 수직 거리(m). 깊이 버퍼로 바닥 점의 월드 좌표를 복원해 수면 y와 뺀다.
	float depth = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	view.xyz /= view.w;
	vec3 floor_world = (INV_VIEW_MATRIX * vec4(view.xyz, 1.0)).xyz;
	float water_depth = max(world_pos.y - floor_world.y, 0.0);

	vec3 color = mix(shallow_color.rgb, deep_color.rgb, clamp(water_depth / depth_fade, 0.0, 1.0));

	float wobble = sin(world_pos.x * 1.3 + TIME * 0.5) * sin(world_pos.z * 1.1 + TIME * 0.4) * foam_wobble;
	float edge = foam_width + wobble;
	float foam = 1.0 - smoothstep(edge - 0.12, edge + 0.12, water_depth);   // 부드러운 가장자리: 0.5 m 격자 해안선의 톱니를 가린다
	color = mix(color, foam_color.rgb, foam);

	vec2 uv_a = world_pos.xz * uv_scale + vec2(1.0, 0.3) * TIME * scroll_speed;
	vec2 uv_b = world_pos.xz * uv_scale * 1.7 + vec2(-0.6, 1.0) * TIME * scroll_speed;

	ALBEDO = color;
	ALPHA = 1.0;
	ROUGHNESS = 0.15;
	SPECULAR = 0.4;
	METALLIC = 0.0;
	NORMAL_MAP = mix(texture(normal_a, uv_a).rgb, texture(normal_b, uv_b).rgb, 0.5);
	NORMAL_MAP_DEPTH = normal_depth;
}
