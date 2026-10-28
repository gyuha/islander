# Recipe round: `tools/blender/player_human.py` (edit the EXISTING script; do NOT run blender)

Repository: /Users/gyuha/workspace/dongval
Reference image (attached): `assets/concept/player_human_turnaround.png`.
Spec: `docs/assets/player_human.md`. This recipe overrides the spec where they conflict.
Do NOT touch `tools/blender/player_bunny.py` or any player_bunny file. Do NOT run `blender`.

## HAIR — delete all separate tuft balls. Build ONE hair mesh.
1. Start from a UV sphere (≈16 segments × 10 rings) slightly larger than the skull: scale ~1.08 relative to the face sphere.
2. Keep only the upper ~60% of the sphere: delete vertices below the ears line at the back and sides, and above the eyebrow line at the front. Result reads as a cap over crown, back and sides.
3. Sculpt procedurally:
   a. **Fringe** — displace the front rim DOWNWARD in 3–4 rounded scallops over the forehead. The scallops stop above the eyes (no hair below the eyebrow line).
   b. **Lumps** — 4–6 soft lumps on the surface: move vertices outward by 0.01–0.02 m with a smooth falloff, for a messy-tufted feel.
   c. **Flicks** — a couple of rounded flicks at the back (outward/upward bulges, rounded, NO up-pointing spikes).
4. Add a Solidify modifier, thickness 0.02 m, so there are no holes. Apply it.
5. Merge the hair into `Head` as part of the Head object (still ONE `Head` object, no new object names).
6. No hair vertex may be in front of the face area (z must stay behind the face front surface, i.e. not cover the eyes, cheeks or mouth).
7. Keep the ears (small rounded ears on the head sides, merged into Head).

## SMOOTH CLAY LOOK — all parts
- Reduce base segment counts first, then add a Subdivision Surface modifier at level 1, apply it before export.
- Shade smooth everywhere. Remove any flat-shaded or auto-smooth split normals.
- Limbs as 8-sided capsules before subdivision.
- Boots and legs: rounded, not boxes (rounded capsule/ellipsoid shapes).
- Triangle total must be ≤ 3,000 (hard limit). Lower base resolution to fit if needed.

## Keep unchanged
- Object names: `PlayerHuman`, `Body`, `Head`, `ArmL`, `ArmR`, `LegL`, `LegR`, `ToolSocket`. No separate hair, ear, or face objects.
- Pivots (world, Godot coords, ±0.01 m): PlayerHuman (0,0,0), Body (0,0.20,0), Head (0,0.52,0), ArmL (+0.18,0.46,0), ArmR (−0.18,0.46,0), ToolSocket (−0.18,0.30,0.03), LegL (+0.08,0.20,0), LegR (−0.08,0.20,0).
- Bbox: height 0.95 (max y 0.95 ±0.01, min y 0), width ≈ 0.46 X (±0.01), face +Z.
- Six materials: `M_skin`, `M_trunk`, `M_cream`, `M_orange`, `M_ink`, `M_blush` (roughness 0.85, sRGB→linear as before).
- Eyes, cheeks, mouth, scarf, backpack, shirt and shorts stay as in the current script. Apply rotation and scale only.
- Apply all modifiers before export.

## Face-direction check (fix this assertion sensibly)
Replace the existing face-direction assertion. Use the eye (`M_ink`) vertices only, and check that their mean z (Godot, world) is greater than the mean z of the Head's skin vertices by at least 0.05 m. This tests that the face points +Z without being fooled by cheek discs wrapping the sides.

## Verification print
Keep the single JSON verification print and its asserts, updating only what this recipe changes (triangle limit stays 3,000; face-direction check as above; add `hair_vertices_front_of_face == 0` if easy).

## Final message
Give: the expected triangle count from your static calculation, the expected bbox, a short list of what you changed, and any recipe step you could not do exactly. Do not run blender.
