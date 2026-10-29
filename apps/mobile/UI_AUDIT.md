# Orin Android UI audit

## Scope and evidence

Code audit of every file in `apps/mobile`, the shared API contracts, and the web identity in `apps/web/src/workspace-theme.css`. No physical-device interaction was performed after the redesign specification prohibited it. The configured emulator system image does not currently boot Android services reliably, so visual findings remain unverified until an isolated emulator is repaired.

## Structural findings

1. Iconography mixed Lucide components with Unicode symbols and text glyphs. This produced inconsistent weight, alignment, accessibility, and active states.
2. Shared colors had recently moved toward the web palette, but workspace colors and several feature treatments still used unrelated purple, blue, teal, and orange accents.
3. Cards were used as the default container for lists, profiles, projects, settings, and operations. This weakened hierarchy and made dense screens feel like generic dashboards.
4. Inputs, sheets, navigation icons, and buttons used different radii and oversized rounded treatments that did not match the web system.
5. Uppercase eyebrow labels appeared on nearly every screen, creating repetitive visual noise and very small metadata text.
6. Tasks and projects preserved real backend behavior, but their rows lacked a consistent custom icon language and relied on glyph chevrons and checkmarks.
7. The More screen exposed all secondary features in one long undifferentiated group. Workspace and account actions were visually mixed with planning tools.
8. Authentication lacked password visibility control and stronger keyboard-aware composition.
9. Screen implementations use large inline render expressions and repeated row styling, increasing the risk of inconsistent states and accessibility regressions.
10. The current tests cover API behavior but do not cover navigation, form state, icon rendering, or failure recovery.

## Accessibility risks

- Several icon-only and checkbox-like controls were rendered as text without a consistent accessible target.
- Some metadata text was 10 or 11 pixels and likely too small on narrow Android devices.
- Repeated compact controls approached the minimum touch target without a shared enforcement rule.
- Screen-level loading is represented only by a spinner and may not announce state changes.
- Visual accessibility, TalkBack order, keyboard behavior, and contrast cannot be certified without a working isolated render target.

## Implementation priorities

1. Centralize tokens, custom icons, navigation, inputs, sheets, rows, and state feedback.
2. Rebuild the application shell and authentication.
3. Replace card-heavy task, project, writing, and home layouts with purposeful lists and sections.
4. Reorganize secondary navigation and workspace controls.
5. Refine planning, operations, settings, error, empty, loading, and destructive states.
6. Add focused component tests, compile Android, then complete a final static audit.
