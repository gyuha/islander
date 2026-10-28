# 아키텍처 개요 · 파일 목록 · 빌드 순서

## 설계 원칙

시스템은 세 층으로 나뉜다. 데이터(Resource `.tres`, JSON), 전역 상태(Autoload `WorldClock`, `ItemDB`), 행동(씬에 붙는 컴포넌트)이다. 컴포넌트끼리는 시그널로 연결하고 UI는 폴링하지 않는다. 테스트 대상 로직은 순수 static 함수나 `tick()`·주입 Callable로 분리해 씬 트리 없이 검증한다. 스킬 스크립트는 `scripts/vendor/gdskills/`로 복사해 고쳐 쓰고 상단에 출처 주석을 단다.

| 문서 | 범위 |
|---|---|
| [data-inventory-crafting.md](data-inventory-crafting.md) | ItemData, InventoryData, 레시피 JSON, ItemDB, CraftingProcessor |
| [world-island.md](world-island.md) | IslandGenerator, 배치, 내비, 물 |
| [player-vitals-interaction.md](player-vitals-interaction.md) | Player, CameraRig, Vitals, Interactable, Harvestable, 물리 레이어 |
| [enemies-ai.md](enemies-ai.md) | Enemy 상태 머신, Slime, Crab, SmartNavigationAgent, EnemySpawner |
| [worldclock-ui.md](worldclock-ui.md) | WorldClock, 조명 전환, HUD, 인벤토리/제작 패널 |
| [testing-capture.md](testing-capture.md) | 헤드리스 테스트 러너, 캡처 모드, Main |
| [../gdd.md](../gdd.md) | 수치 튜닝표 |
| [../art/style-guide.md](../art/style-guide.md) | 색, 환경, 카메라, 물 |

## project.godot 설정

| 키 | 값 |
|---|---|
| `application/run/main_scene` | `res://scenes/main.tscn` |
| `rendering/renderer/rendering_method` | `forward_plus` |
| `display/window/size/viewport_width × height` | 1600 × 900 |
| `rendering/anti_aliasing/quality/msaa_3d` | 4x |
| Autoload | `WorldClock` = `res://autoload/world_clock.gd`, `ItemDB` = `res://autoload/item_db.gd` (이 순서) |
| 3D 물리 레이어 이름 | 1 `world`, 2 `player`, 3 `enemy`, 4 `interact` |
| InputMap | `move_forward` W, `move_back` S, `move_left` A, `move_right` D, `sprint` Shift, `interact` E, `attack` 마우스 왼쪽, `toggle_inventory` Tab, `toggle_crafting` C, `camera_zoom_in` 마우스 휠 위, `camera_zoom_out` 마우스 휠 아래. `ui_cancel`(Esc)은 Godot 기본 액션을 그대로 쓴다(등록 불필요) |
| `gui/theme/custom` | `res://assets/ui/theme.tres` (기본 폰트 NanumSquareRoundR, `worldclock-ui.md` 테마 절) |

## main.tscn 노드 트리

```
Main (Node3D, scripts/main.gd)
├─ WorldEnvironment            # Environment + ProceduralSkyMaterial (style-guide 값)
├─ Sun (DirectionalLight3D)
├─ Island (instance scenes/world/island.tscn)
├─ Water (instance scenes/world/water.tscn)
├─ Player (instance scenes/player/player.tscn, island_path = ../Island, camera_rig_path = ../CameraRig)
├─ CameraRig (instance scenes/player/camera_rig.tscn, target_path = ../Player)   # Pitch → SpringArm(SpringArm3D) → Camera3D, 마우스 모드 소유
├─ Enemies (Node3D)
├─ EnemySpawner (Node3D, enemy_spawner.gd)
└─ HUD (instance scenes/ui/hud.tscn)
```

## 전체 파일 목록

```
project.godot
autoload/world_clock.gd
autoload/item_db.gd
data/items/{wood,stone,berry,stone_axe,stone_pickaxe,wooden_spear}.tres
data/recipes.json
scripts/main.gd
scripts/vendor/gdskills/item_data.gd              ← inventory_system_inventory_item_resource.gd (InventoryItem → ItemData)
scripts/vendor/gdskills/item_slot.gd              ← inventory_system_item_slot_data.gd
scripts/vendor/gdskills/inventory_data.gd         ← inventory_system_inventory_data_resource.gd
scripts/vendor/gdskills/interactable.gd           ← genre_survival_interactable.gd
scripts/vendor/gdskills/vitals.gd                 ← genre_survival_status_depletion_manager.gd (StatusDepletionManager → Vitals)
scripts/vendor/gdskills/smart_navigation_agent.gd ← navigation_pathfinding_smart_navigation_agent.gd
scripts/vendor/gdskills/island_noise.gd           ← procedural_generation_fast_noise_noise2d_master.gd (+ class_name IslandNoise)
scripts/vendor/gdskills/poisson_disk_sampler.gd   ← procedural_generation_poisson_disk_sampling_2d.gd (+ class_name PoissonDiskSampler)
scripts/crafting/crafting_processor.gd            ← genre_survival_crafting_recipe_processor.gd 흐름 (CraftingRecipeProcessor → CraftingProcessor)
scripts/world/island_generator.gd
scripts/world/island_layout.gd
scripts/world/harvestable.gd
scripts/player/player.gd
scripts/player/camera_rig.gd
scripts/enemies/enemy.gd
scripts/enemies/slime.gd
scripts/enemies/crab.gd
scripts/enemies/enemy_spawner.gd
scripts/ui/{hud,slot_widget,inventory_panel,crafting_panel,recipe_row}.gd
scenes/main.tscn
scenes/player/{player,camera_rig}.tscn
scenes/world/{island,water,pine_tree,palm_tree,rock,berry_bush,boat,buoy}.tscn
scenes/enemies/{slime,crab}.tscn
scenes/ui/{hud,slot_widget,inventory_panel,crafting_panel,recipe_row}.tscn
shaders/water.gdshader
assets/ui/theme.tres
assets/fonts/NanumSquareRoundR.ttf               ← 공식 배포본에서 개발자가 직접 입수 (worldclock-ui.md 폰트 절)
assets/fonts/NanumSquareRoundB.ttf
assets/fonts/OFL.txt                              ← 폰트 라이선스 전문 (필수)
assets/ui/icons/{wood,stone,berry,stone_axe,stone_pickaxe,wooden_spear}.png
assets/models/{pine_tree,palm_tree,rock,berry_bush,player_human,slime,crab,boat,buoy}/<name>.glb
tools/blender/<name>.py
tests/run_tests.gd
tests/test_case.gd
tests/test_{inventory,crafting,vitals,island,spawner}.gd
captures/.gdignore
```

가져오지 않는 스킬 스크립트: `genre_survival_inventory_data.gd`(InventoryData 중복), `genre_survival_modular_inventory_controller.gd`, `genre_survival_survival_patterns.gd`(필요한 두 패턴만 인라인), AStar `AIPathingSystem`(2D), 절차 생성 메셔(스텁).

## 사용하는 class_name (프로젝트 안에서 유일해야 함)

`ItemData`, `ItemSlot`, `InventoryData`, `CraftingProcessor`, `Interactable`, `Harvestable`, `Vitals`, `Player`, `CameraRig`, `IslandGenerator`, `IslandNoise`, `PoissonDiskSampler`, `SmartNavigationAgent`, `Enemy`, `Slime`, `Crab`, `EnemySpawner`, `HUD`, `SlotWidget`. Autoload 스크립트(`world_clock.gd`, `item_db.gd`)와 테스트 파일에는 class_name을 붙이지 않는다.

## 빌드 순서

각 단계는 끝날 때 `godot --headless --path . --import` → `godot --headless --path . --quit`에서 `ERROR`/`SCRIPT ERROR` 0, 그리고 해당 테스트 통과가 조건이다. 에셋이 없으면 플레이스홀더(기본 도형)로 진행한다.

1. **골격**: project.godot(위 표), 디렉터리, 빈 `main.tscn`, Autoload 2개 → 검증: import/quit 오류 0
2. **데이터·인벤토리·제작**: vendored item_data/item_slot/inventory_data, `.tres` 6개, recipes.json, ItemDB, CraftingProcessor, 테스트 러너 + test_inventory/test_crafting → 검증: 러너 통과
3. **지형·배치**: island_noise, poisson_disk_sampler, IslandGenerator(플레이스홀더 채집물), 물 셰이더, 내비 베이크, test_island → 검증: 테스트 통과 + 창 실행 시 섬 표시
4. **플레이어·Vitals·채집**: Player, CameraRig(SpringArm 궤도 카메라, 마우스 캡처·Esc 해제·클릭 재캡처), Vitals, Interactable, Harvestable, test_vitals → 검증: 테스트 + 수동 확인(마우스로 궤도 회전·pitch 제한·휠 줌, 나무 줄기 뒤로 돌려도 카메라가 뚫지 않음, WASD가 카메라 기준, 맨손 채집)
5. **시간·UI**: 나눔스퀘어라운드 폰트 + `OFL.txt` + `theme.tres` + `gui/theme/custom`, WorldClock 조명, HUD(`panels_changed` → 마우스 모드), 패널, 캡처 모드(고정 카메라 자세) → 검증: `-- --capture`로 PNG 2장(한글이 네모로 깨지지 않음) + 수동 확인(Tab/C 열면 커서 보이고 시점 고정, 닫으면 재캡처, Esc 동작)
6. **몬스터**: SmartNavigationAgent, Enemy/Slime/Crab, EnemySpawner, test_spawner → 검증: 테스트 + 밤 추적 수동 확인
7. **에셋 교체**: glb·아이콘 연결, 환경값 최종 조정 → 검증: 캡처를 참조 이미지와 비교

```
골격 → 데이터·제작 → 지형·배치 → 플레이어·채집 → 시간·UI → 몬스터 → 에셋 교체
```
