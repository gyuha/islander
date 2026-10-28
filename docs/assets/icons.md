# 에셋 명세: 아이템 아이콘 6종

| 항목 | 값 |
|---|---|
| 용도 | 인벤토리·제작 패널 슬롯 아이콘 (화면 표시 56×56) |
| 출력 | `assets/ui/icons/<id>.png` |
| 형식 | PNG 128×128, RGBA, **실제 알파 채널이 있는 투명 배경** |
| 여백 | 사방 8 px 안에 물체가 들어오게(물체 최대 112×112), 중앙 정렬 |
| 스타일 | `docs/art/style-guide.md` 7절: 클레이 3D 렌더, 3/4 시점(약 30° 위), 왼쪽 위 광원, 외곽선 없음, 바닥 그림자 없음, 글자 없음 |
| 색 | 아래 표의 팔레트 hex만 사용 (style-guide 2절) |

6장 모두 같은 시점·광원·크기 비율로 한 세트처럼 보여야 한다. 작은 크기에서 읽히도록 실루엣을 크고 단순하게 한다.

| id | 파일 | 내용 | 주요 색 |
|---|---|---|---|
| `wood` | `assets/ui/icons/wood.png` | 둥근 통나무 2개를 X자로 겹침, 단면에 나이테 원 2개 | trunk `#8A5A3B`, 단면 wood_light `#BE946D` |
| `stone` | `assets/ui/icons/stone.png` | 둥근 회청 돌 덩어리 2개(큰 것 + 작은 것) | stone `#9BA7A6`, stone_light `#C4CDCB` |
| `berry` | `assets/ui/icons/berry.png` | 빨간 베리 3알 송이 + 초록 잎 1장 | red `#DD5161`, leaf `#3FA463` |
| `stone_axe` | `assets/ui/icons/stone_axe.png` | 나무 자루(대각선, 좌하→우상) 끝에 둥근 돌 도끼날, 끈 묶음 | wood_light, stone, 끈 cream `#F2E7BB` |
| `stone_pickaxe` | `assets/ui/icons/stone_pickaxe.png` | 나무 자루 끝에 양쪽으로 뻗은 둥근 돌 곡괭이 머리, 끈 묶음 | wood_light, stone, cream |
| `wooden_spear` | `assets/ui/icons/wooden_spear.png` | 대각선 긴 나무 자루 + 뾰족하지만 끝이 둥근 나무 촉, 촉 아래 주황 끈 | wood_light, wood_dark `#876C46`, orange `#E79C62` |

## 검수

- 6개 파일 모두 128×128, 모드 RGBA, 네 모서리 픽셀 알파 = 0.
- 물체가 테두리 8 px 안쪽에 있음.
- 6장을 나란히 놓았을 때 광원 방향·채도가 일치.
