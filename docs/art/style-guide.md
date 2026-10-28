# 아트 스타일 가이드

참조: `assets/concept/reference.webp` (같은 섬을 4가지 분위기로 그린 600×1200 이미지. 위에서 1·2번째 패널은 진한 청록 저녁 톤, 3번째는 맑은 낮, 4번째는 겨울). **게임의 낮은 3번째 패널, 밤은 1번째 패널의 청록 톤**을 목표로 한다.

## 1. 형태 언어

참조의 모든 물체는 "손으로 빚은 점토 장난감"처럼 두툼하고 모서리가 둥글다. 날카로운 모서리와 얇은 판은 없다.

- **덩어리 우선**: 실루엣은 큰 덩어리 2~4개로 읽혀야 한다. 세부(창틀, 나뭇결)는 형태가 아니라 색 덩어리로 표현.
- **베벨**: 모든 박스형 모서리에 베벨. 폭 = 해당 부품 가장 짧은 변의 10~15%, 세그먼트 2~3. Blender: Bevel 모디파이어(Limit Method: Angle 30°) → 적용.
- **셰이딩**: 스무스 셰이딩 + Auto Smooth(Smooth by Angle) 40°. 면이 각지게 보이는 플랫 셰이딩 금지. "로우폴리"는 삼각형 예산의 의미이지 각진 표현이 아니다.
- **비례**: 캐릭터는 머리가 전체 높이의 40~45%(2~2.5등신), 팔다리는 짧고 굵게. 나무는 줄기가 짧고 수관이 크다(수관 높이 ≥ 전체의 65%).
- **부풀림**: 원뿔·원기둥도 옆면을 살짝 부풀린다(중간 반지름 +5~8%). 아래 가장자리는 둥근 립(lip) 처리 — 참조의 소나무 단마다 아래가 말려 있는 형태.
- **지면 접촉**: 바닥 원점에 놓았을 때 살짝 파묻혀도 어색하지 않게 밑면은 평평하게.

## 2. 팔레트 (참조에서 추출, sRGB hex)

참조 패널 1·3을 미디언컷 28색으로 양자화해 뽑은 값을 역할별로 정리했다. 에셋은 이 표의 색만 쓴다(명세서에 적힌 추가 색 예외).

| 역할 | 이름 | hex | 출처 |
|---|---|---|---|
| 바다 낮 깊음 | sea_day_deep | `#47A693` | 패널3 |
| 바다 낮 얕음 | sea_day_shallow | `#7FD3C4` | 패널3 `#85D6BB`·`#6AB7AA` 사이 |
| 바다 밤 깊음 | sea_night_deep | `#0B6965` | 패널1 최다색 |
| 바다 밤 얕음 | sea_night_shallow | `#1C8A7A` | 패널1 `#09836D` 계열 |
| 물거품 | foam | `#EAF8F3` | 섬 둘레 흰 띠 |
| 하늘 위 / 수평선 | sky_top / sky_horizon | `#8ED3E0` / `#C9EEF0` | 패널3 `#9EDAE2`·`#BFE9ED` |
| 풀 1단 | grass | `#5DB85E` | `#4CB45E`·`#75B86C` |
| 풀 2단(밝음) | grass_light | `#79C46A` | |
| 잎 진함 | leaf_dark | `#2F8F57` | `#318F58` |
| 잎 중간 | leaf | `#3FA463` | `#439D55` |
| 잎 그늘 | leaf_shadow | `#285538` | |
| 야자 잎 | palm_leaf | `#6DB33F` | 패널1 야자 `#69941E`를 밝게 |
| 흙 옆면 | earth | `#C36F46` | 패널3 |
| 흙 진함 | earth_dark | `#985033` | |
| 흙 지층 띠 | earth_band | `#B4643F` | 신규, earth↔earth_dark 35% 보간. 절벽 벽의 가로 지층 띠 (`docs/architecture/world-island.md` 메시 절) |
| 모래 | sand | `#E4C799` | 패널3 해변 |
| 나무(목재) 밝음 | wood_light | `#BE946D` | 데크 |
| 나무(목재) 진함 | wood_dark | `#876C46` | |
| 줄기 | trunk | `#8A5A3B` | |
| 주황 포인트(지붕) | orange | `#E79C62` | 패널1·3 공통 |
| 노랑 포인트 | yellow | `#FDE254` | 지붕 줄무늬 |
| 빨강 포인트 | red | `#DD5161` | 등대 줄무늬 |
| 적갈 | rust | `#8C341F` | |
| 크림 | cream | `#F2E7BB` | |
| 흰색(구름·부표·눈 흰자) | white_warm | `#F9F6E5` | 참조의 흰 동물 인형·구름 |
| 돌 | stone | `#9BA7A6` | 참조에 큰 바위가 없어 회청 중간값으로 정함 |
| 돌 밝음 | stone_light | `#C4CDCB` | |
| 짙은 선/눈 | ink | `#2B2233` | |
| 볼 터치 | blush | `#F2A0B8` | |
| 피부 | skin | `#F2C6A0` | 신규, 플레이어 피부. blush 볼과 cream 셔츠 사이에서 구분되는 따뜻한 복숭아색 (`docs/assets/player_human.md`) |
| 슬라임 | slime | `#9C7BD6` | 신규, 라벤더(초록·청록과 보색 대비) |
| 슬라임 밝음 | slime_light | `#B9A0E6` | 슬라임 윗면 하이라이트 (`docs/assets/slime.md`) |
| 게 | crab | `#E0573A` | 신규 |

## 3. 머티리얼 (무광 클레이)

- 에셋 모델: 색마다 머티리얼 1개(`M_<팔레트 이름>`, 예 `M_leaf_dark`). Principled BSDF: Roughness 0.85, Metallic 0, Specular IOR Level 0.3, 텍스처 없음. 에셋당 머티리얼 ≤ 6개.
- **색 공간 주의**: 표의 hex는 sRGB다. Blender 파이썬에서 Base Color에 넣을 때는 선형으로 변환한다: `c <= 0.04045 ? c/12.92 : ((c+0.055)/1.055)^2.4`. 변환 없이 넣으면 Godot에서 색이 바래 보인다.
- 지형: 버텍스 컬러 + `StandardMaterial3D`(roughness 0.9, specular 0.3). 고원 윗면 풀(1단 grass, 2·3단 grass_light), 둥근 풀 립 밑면 leaf_dark, 절벽 벽 earth와 earth_band 가로 띠 교대, 벽 발치 earth_dark, 해변·경사로 길 sand, 경사로 옆 비탈 earth.
- 발광·금속·반사 없음. 유일한 예외는 물.

## 4. 조명 · 환경 (Godot `WorldEnvironment`)

참조는 부드러운 주광, 짙은 접촉 그림자(AO), 채도 높은 색, 약한 블룸이 특징이다.

### 고정값

| 속성 | 값 |
|---|---|
| `background_mode` | `BG_SKY`, Sky = `ProceduralSkyMaterial` |
| `ambient_light_source` | `AMBIENT_SOURCE_COLOR` |
| `tonemap_mode` | `TONE_MAPPER_FILMIC`, `tonemap_exposure 0.95`, `tonemap_white 6.0` |
| `ssao_enabled` | true, `radius 1.6`, `intensity 3.2`, `power 1.5`, `detail 0.5`, `horizon 0.06`, `sharpness 0.98`, `light_affect 0.3`, `ao_channel_affect 0` |
| `ssil_enabled`, `sdfgi_enabled`, `volumetric_fog_enabled`, `fog_enabled` | false |
| `glow_enabled` | true, `glow_intensity 0.4`, `glow_strength 1.0`, `glow_bloom 0.05`, `glow_blend_mode GLOW_BLEND_MODE_SOFTLIGHT`, `glow_hdr_threshold 1.0`, levels 3·4·5만 켬 |
| `adjustment_enabled` | true, `brightness 1.0`, `contrast 1.1`, `saturation 1.12` |
| Sun `rotation_degrees` | `(-50, -25, 0)` — 시작·캡처 카메라(yaw 35°) 기준 왼쪽 앞 위에서 비춰 오른쪽 뒤로 그림자. 카메라를 돌리면 화면상 광원 방향도 따라 바뀐다(의도된 동작) |
| Sun 그림자 | `shadow_enabled true`, `shadow_blur 3.0`, `directional_shadow_mode PARALLEL_4_SPLITS`, `directional_shadow_max_distance 60` |

### 낮/밤 조명 값 (`WorldClock`이 12초 Tween)

| 속성 | 낮 | 밤 |
|---|---|---|
| Sun `light_color` / `light_energy` | `#FFF3DE` / 1.0 | `#9DB8FF` / 0.3 |
| `ambient_light_color` / `ambient_light_energy` | `#CFEDEA` / 0.48 | `#2E6B78` / 0.55 |
| Sky `sky_top_color` | `#8ED3E0` | `#0A2E3A` |
| Sky `sky_horizon_color`, `ground_horizon_color` | `#C9EEF0` | `#145A5C` |
| Sky `ground_bottom_color` | `#47A693` | `#0B4F4C` |
| Water `shallow_color` / `deep_color` | `#7FD3C4` / `#47A693` | `#1C8A7A` / `#0B6965` |
| Water `foam_color` | `#EAF8F3` | `#9FD9CF` |

밤에도 섬 형태가 읽혀야 한다. 캡처한 밤 화면에서 풀 색이 검게 뭉개지면 ambient energy를 0.05씩 올린다.

## 5. 카메라

고정 쿼터뷰 대신 마우스로 도는 3인칭 궤도 카메라를 쓴다(구조·입력은 `docs/architecture/player-vitals-interaction.md`의 CameraRig, 수치 원본은 GDD 5절 "카메라" 표). 시작 자세를 높은 각도로 잡아 참조처럼 "위에서 내려다본 섬"으로 읽히게 한다.

- 투영: 원근, 세로 `fov 50`(16:9에서 가로 약 79°), near 0.1, far 200. 3인칭 근접 시점에서 30°는 너무 답답하고, 60°는 화면 가장자리에서 둥근 클레이 형태가 늘어나 보여 그 사이 50°로 정했다.
- 시작·캡처 자세: yaw 35°, pitch −35°, 거리 7 m, 피벗 = 플레이어 발 + 0.9 m. 카메라 높이 ≈ 4.9 m.
- 시작 자세에서 보이는 지면(평지 기준 계산): 플레이어 뒤 약 2.9 m ~ 앞 약 22 m, 피벗 거리에서 화면 폭 약 11.6 m. 화면 위 경계가 수평선 아래 10°라 하늘은 보이지 않는다. 하늘은 pitch를 −25°보다 위로 올릴 때부터 보인다.
- 사용자 조작 범위: pitch −70° ~ −5°, 거리 3 ~ 12 m. 낮은 pitch에서 수평선·하늘이 보이는 것은 허용한다(낮/밤 하늘 색이 style-guide 4절 값으로 정해져 있음).
- 그림자 거리 `directional_shadow_max_distance 60`은 시작 자세의 가시 범위(앞 ~22 m)를 덮으므로 그대로 둔다.
- 피사계 심도·비네트 같은 후처리는 MVP에서 쓰지 않는다.

## 6. 물

- 단색 평면 + 수심 그라데이션 + 해안 거품 띠. 사실적 반사·굴절 없음.
- 수심은 수면에서 바닥까지의 **수직 거리**(m)다. 카메라 각도와 무관하다(셰이더 식은 `world-island.md` 물 절).
- 수심 0 → `depth_fade`(**1.2 m**, 이전 1.8) 사이를 `shallow_color` → `deep_color`로 보간. 참조처럼 섬 둘레가 밝은 띠로 보여야 한다. 지형 물속 단면과 합치면 물가선에서 약 0.7~5 m가 밝은 청록 고리, 그 바깥이 깊은색이다.
- 불변식: `depth_fade ≤ |해저 높이| − 0.5`(해저 −2.0). 이를 어기면 해저 격자가 깊은색까지 포화하지 못해 격자 경계 사각형이 보인다.
- 거품: 수심 < `foam_width`(0.35 m)에서 `foam_color`, 가장자리는 노이즈로 살짝 일렁임(0.05 m). 참조 섬 둘레의 흰 테두리. 물가선에서 약 0.7 m 폭.
- 표면: 저주파 노이즈 노멀 2장을 서로 다른 방향으로 천천히 스크롤(속도 0.02), roughness 0.15, specular 0.4 — 햇빛 반짝임이 약하게만 보이게.
- 정점 파도 없음(평면 유지, 보트·부표는 Tween으로 흔듦).

## 7. UI 아이콘 스타일

모델과 같은 클레이 3D 렌더 느낌. 3/4 시점(약 30° 위에서), 왼쪽 위 광원, 부드러운 접촉 그림자 없음, 외곽선 없음, 배경 투명. 상세는 `docs/assets/icons.md`.
