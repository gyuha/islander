# Polish round: `tools/blender/player_human.py` (edit the EXISTING script; do NOT run blender)

Repository: /Users/gyuha/workspace/dongval
Reference image (attached): `assets/concept/player_human_turnaround.png`. Match its hair, face and soft clay look.
Spec: `docs/assets/player_human.md`. This polish request overrides the spec where they conflict (listed below).

Do NOT touch `tools/blender/player_bunny.py` or any player_bunny file. Do NOT run `blender`.

## Changes to make
1. **Hair** — rebuild as 6–9 overlapping soft rounded tufts (flattened ellipsoids or teardrops) sweeping forward/sideways, with a fringe over the forehead. NO spikes or cones pointing up. Hair must not cover the face (eyes, cheeks, mouth stay visible). Remove the current helmet cap and horn-like bumps. Hair stays merged into `Head` (no new object names). Keep the highest point of the whole model at y = 0.95 ±0.01 (a tuft may define it).
2. **Ears** — add two small rounded ears on the head sides (±X), merged into `Head` geometry. Do NOT create separate objects. Object list stays unchanged: `PlayerHuman`, `Body`, `Head`, `ArmL`, `ArmR`, `LegL`, `LegR`, `ToolSocket`. The old "no ear mesh" check is replaced by "no separate ear objects" (this overrides spec 검수).
3. **Face** — eyes bigger: vertical ovals ≈ 0.07 wide × 0.09 tall, each with a small cream highlight (sphere ~0.02) on the upper-outer side. Cheeks bigger and softer: flattened discs ≈ 0.09 diameter, blush colour. Small smile: short curved capsule under the nose line. Keep the eye spacing ≈ 0.15 apart.
4. **Smooth clay look** — every mesh part shades SMOOTH (no faceting). Apply smooth shading to all mesh objects and use smooth-by-angle with 40° or weighted normals so bevels read as rounded. Keep bevels, but the normals must look soft.
5. **Triangles** — use more segments on Head and Body for roundness if budget allows. Trim elsewhere (boots, backpack, straps) so the total is ≤ 2,800 (target) and never above 3,000 (hard limit).

## Keep unchanged (spec checks)
- Pivots (world, Godot coords, ±0.01 m): PlayerHuman (0,0,0), Body (0,0.20,0), Head (0,0.52,0), ArmL (+0.18,0.46,0), ArmR (−0.18,0.46,0), ToolSocket (−0.18,0.30,0.03), LegL (+0.08,0.20,0), LegR (−0.08,0.20,0).
- Bbox: X width 0.46 ±0.01, min y 0, max y 0.95 ±0.01, face +Z.
- Materials exactly six: `M_skin`, `M_trunk`, `M_cream`, `M_orange`, `M_ink`, `M_blush` (roughness 0.85, sRGB→linear as before).
- Apply rotation and scale only (location stays as pivot offsets).
- Keep the self-verification JSON print and its asserts. Update only the asserts this polish changes (ear check, triangle budget).

## Final message
Give: the new triangle count from your static calculation, the bbox you expect, and a short list of what you changed. Do not run blender.
