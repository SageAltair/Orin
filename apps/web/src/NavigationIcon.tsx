import type { SVGProps } from "react";
import type { CapabilityId } from "./capabilities";

type IconProps = SVGProps<SVGSVGElement> & { id: CapabilityId; size?: number };

/** A compact, platform-neutral navigation set, drawn specifically for Orin. */
export function NavigationIcon({ id, size = 19, ...props }: IconProps) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.65, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const paths: Record<CapabilityId, React.ReactNode> = {
    home: <><path d="M3.5 10.5 12 3.5l8.5 7v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"/><path d="M9 20.5v-7h6v7"/></>,
    opportunities: <><circle cx="12" cy="12" r="8.5"/><path d="m15.6 8.4-2.1 5.1-5.1 2.1 2.1-5.1z"/></>,
    calendar: <><rect x="3.5" y="5.5" width="17" height="15" rx="2"/><path d="M7.5 3.5v4m9-4v4m-13 3h17M8 14h3m3 0h3M8 17.5h3"/></>,
    projects: <><path d="M3.5 7.5v11a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-6l-2-3h-5a2 2 0 0 0-2 2z"/></>,
    tasks: <><rect x="3.5" y="4" width="17" height="16" rx="2"/><path d="m7 9 1.5 1.5L11 8m2.5 1h4M7 15l1.5 1.5L11 14m2.5 1h4"/></>,
    activity: <><path d="M3 12h4l3-6 4 12 3-6h4"/></>,
    memories: <><path d="M12 6.5c-2-1.5-4.5-2-8-1.5v14c3.5-.5 6 0 8 1.5 2-1.5 4.5-2 8-1.5V5c-3.5-.5-6 0-8 1.5zM12 6.5v14"/></>,
    focus: <><circle cx="12" cy="13" r="8"/><path d="M12 13V8m0 5 3 2M9 2.5h6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M10 3.5h4l.6 2.1 1.7.8 2-.9 2.5 3-.9 1.9.3 1.6.9 2-2.5 3-2-.9-1.7.8-.6 2.1h-4l-.6-2.1-1.7-.8-2 .9-2.5-3 .9-2-.3-1.6-.9-1.9 2.5-3 2 .9 1.7-.8z"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false" {...common} {...props}>{paths[id]}</svg>;
}
