export type CapabilityId = "home" | "projects" | "tasks" | "activity" | "settings";
export type Density = "comfortable" | "compact";
export type Theme = "light" | "dark" | "system";

export interface UserPreferences {
  visibleCapabilities: CapabilityId[];
  hiddenCapabilities: CapabilityId[];
  pinnedCapabilities: CapabilityId[];
  density: Density;
  theme: Theme;
  autonomyMode: "conservative" | "balanced" | "automatic" | "custom";
  customAutonomy: Record<string, "automatic" | "approval">;
}

export interface Capability {
  id: CapabilityId;
  label: string;
  description: string;
  icon: string;
}

// Only capabilities currently implemented in this foundation are granted.
export const capabilities: Capability[] = [
  { id: "home", label: "Home", description: "Your current priorities", icon: "⌂" },
  { id: "projects", label: "Projects", description: "Organize work by outcome", icon: "▦" },
  { id: "tasks", label: "Tasks", description: "Keep track of next steps", icon: "☑" },
  { id: "activity", label: "Activity", description: "A record of recent changes", icon: "◷" },
  { id: "settings", label: "Settings", description: "Shape your Orin workspace", icon: "⚙" },
];

export const defaultPreferences: UserPreferences = {
  visibleCapabilities: ["home", "tasks"],
  hiddenCapabilities: ["projects", "activity", "settings"],
  pinnedCapabilities: ["home", "tasks"],
  density: "comfortable",
  theme: "light",
  autonomyMode: "balanced",
  customAutonomy: {},
};

export function getNavigationCapabilities(granted: Capability[], preferences: UserPreferences): Capability[] {
  const visible = new Set(preferences.visibleCapabilities);
  const pinned = new Set(preferences.pinnedCapabilities);
  return granted.filter((capability) => visible.has(capability.id))
    .sort((a, b) => Number(pinned.has(b.id)) - Number(pinned.has(a.id)));
}

export function normalizePreferences(value: unknown): UserPreferences {
  if (!value || typeof value !== "object") return defaultPreferences;
  const candidate = value as Partial<UserPreferences>;
  const validIds = new Set(capabilities.map(({ id }) => id));
  const ids = (items: unknown, fallback: CapabilityId[]) => Array.isArray(items)
    ? [...new Set(items.filter((id): id is CapabilityId => typeof id === "string" && validIds.has(id as CapabilityId)))]
    : fallback;
  const visibleCapabilities = ids(candidate.visibleCapabilities, defaultPreferences.visibleCapabilities);
  return {
    visibleCapabilities,
    hiddenCapabilities: capabilities.map(({ id }) => id).filter((id) => !visibleCapabilities.includes(id)),
    pinnedCapabilities: ids(candidate.pinnedCapabilities, defaultPreferences.pinnedCapabilities).filter((id) => visibleCapabilities.includes(id)),
    density: candidate.density === "compact" ? "compact" : "comfortable",
    theme: candidate.theme === "dark" || candidate.theme === "system" ? candidate.theme : "light",
    autonomyMode: candidate.autonomyMode === "conservative" || candidate.autonomyMode === "automatic" || candidate.autonomyMode === "custom" ? candidate.autonomyMode : "balanced",
    customAutonomy: candidate.customAutonomy && typeof candidate.customAutonomy === "object" ? candidate.customAutonomy as Record<string, "automatic" | "approval"> : {},
  };
}
