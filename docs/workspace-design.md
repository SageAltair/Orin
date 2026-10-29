# Workspace design

The approved Settings design is the shared visual reference for Orin. Warm stone surfaces, muted forest accents, DM Sans interface text, and Manrope headings are used across the shell, projects, tasks, focus, Writing, activity, Calendar, Opportunities, and Ask Orin. Latin variable fonts and their OFL licenses are bundled in `apps/web/public/fonts`; the interface does not depend on a font service.

`apps/web/src/workspace-theme.css` owns the shared palette, spacing, and surface treatments. It loads after the existing feature styles. Feature-specific grids, dialogs, data flows, and permission behavior remain with their existing components. The light, dark, and system palettes all use the same CSS variables. Focus keeps its existing 48px control targets.

Settings opens on Appearance, with a compact section navigator and visual theme previews. Account, workspace personalization and memory, autonomy, approvals, notifications, workers, GitHub, and data export/deletion remain reachable in their sections. Panels stay mounted when changing sections so unfinished forms are retained. Arrow keys, Home, and End move through section navigation; on narrow screens the navigator becomes a horizontal strip contained within the page.

Primary work uses the wide canvas. Secondary content is displayed as quiet lists and open sections. Ask Orin remains available as the floating control; duplicate entry points were removed from the top toolbar and Home.

The redesign changes the real React frontend. It does not replace API behavior with the earlier prototype's simulated assistant or browser-local records, and it does not deploy the production app.
