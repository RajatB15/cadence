# Cadence UI system

Design language: **obsidian and ember**. A deep blue-black base (dark is primary, a warm paper light theme mirrors it), one accent colour per health domain, and light used as the only decoration: a 1px rim, a bright hairline along the top edge of every card, soft ambient shadows, and a glow that follows the part of the day. Numbers are the heroes (heavy Manrope, tabular figures, tight tracking). Motion is short, springy and never required to understand content.

Source of truth: tokens in `app/web/src/index.css` (CSS) and `lib/theme.ts` (`C`, for charts and inline SVG). Keep the two in step.

## Tokens

| Token | Use |
| --- | --- |
| `ink` / `coal` / `slate` | page / card / raised fill and inputs |
| `line`, `line-strong`, `--rim`, `--rim-top` | borders, the 1px card rim, the top highlight |
| `cream` / `paper` / `mute` / `dim` | headings / body / secondary / tertiary text (all >= 4.5:1 on their surface) |
| `gold` energy, `lime` activity, `violet` sleep, `mint` recovery, `coral` heart, `sky` intake and body, `amber` caution | domain accents. Same domain, same colour, everywhere |
| `--shadow-card`, `--shadow-float`, `--glass`, `--pill`, `--shimmer` | depth and glass, flip with the theme |
| `--radius-card` 22, `--radius-tile` 18, `--radius-sheet` 28, chips are pills | radii. Legacy full-border boxes with no `rounded-*` get 14px from a base rule |
| `--ease-spring`, `--ease-out-expo`, `--ease-snap` | motion curves |

Type scale (px): 11 `.eyebrow`, 12 caption, 14 body-small, 16 body, 20 `.t-title`, 28 title, `.t-large` 36 to 60, display 64+. Numbers: `.num` (inline) and `.numeral` (big, tighter). `.mono` is only for code-like text. Never go below 11px.

## Components (all backward compatible)

- `Card` (`components/Card.tsx`): the one card anatomy. Props: `accent` (domain colour, adds `AccentEdge` light), `interactive` (lift + press), `pad`, `as`. Or use the `.surface` class directly. Do not draw hard coloured top or left bars; use `AccentEdge`.
- `Shell` / `PageHeader`: phone gets a floating glass tab bar (active pill morphs with a shared layout id, safe-area aware), desktop a rail with the same morph. `PageHeader` condenses into a glass title bar on scroll through `CondensedTitle` (string titles only).
- `Sheet`: bottom sheet on phone with grabber, spring and drag-to-dismiss; right drawer on desktop.
- `Segmented`, `.pop` (+ `-lime`, `-coral`, `-ghost`), `.chip`, `.press` (any tappable: scale 0.97 spring).
- `LoadingBlock`, `Skeleton`, `.skeleton` (quiet shimmer). Shape a skeleton like the finished layout (`home/HomeSkeleton.tsx`). `ErrorBlock` for failures.
- `EmptyCard` and `RingsIllustration` (`EmptyState.tsx`): inline-SVG empty state, one line of what is missing, one calm next step.
- `Chart` + `chartBase` + `areaFill(color)`, `lineStyle(color)`, `barStyle(color)`, `withAlpha`. Charts go only through `Chart`. Gradient areas fade to transparent; lines have round caps.
- `Sparkline` (draw-in, glow end dot), `CountUp` (numbers settle once, instant under reduced motion).
- Home: `DayRing` (four rings vs stated references, from the pure `lib/dayRing.ts`; a closed ring with fresh data gets a one-off halo), `CalorieRing`, `VitalsRail`, `PhaseHeader`, `NowCard`.

## Motion rules

1. Only `transform` and `opacity` animate; one blur layer per floating surface (tab bar, condensed bar). Film grain is off on touch.
2. Durations: press 80 to 220ms, reveals 450 to 600ms, rings 1.1 to 1.4s. Stagger by index, never more than ~60ms.
3. Everything animated is gated by `prefers-reduced-motion` (CSS `no-preference` blocks or `useReducedMotion`). Content must be complete with motion off.
4. Celebrations are subtle, once, and only for fresh (not stale) data.

## Do / don't

- Do show missing data as a dash or empty track, never zero; mark stale values as from an earlier day.
- Do keep targets at least 44px on touch, text at least 11px, contrast at least 4.5:1 in both themes.
- Do give every new view loading, empty, error and unsupported states.
- Don't hard-code hex colours in components: use tokens or `C`. Light theme accents are deliberately deeper.
- Don't add glass to cards; cards are solid gradient surfaces.
- Don't use bright left borders on rounded cards; use `AccentEdge`, or for legacy markup `className="surface edge"` with `style={edge(color)}` (`lib/color.ts`): clipped by the radius, no corner pinch, no extra blur layer.
