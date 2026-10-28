import type { SVGProps } from "react";

type ActionName = "add" | "close" | "settings" | "menu" | "pin" | "logout" | "copy" | "search" | "message" | "attachment" | "up" | "external" | "command" | "moon" | "sun" | "history" | "list-add" | "more" | "bell" | "check" | "left" | "right" | "filters" | "edit" | "document" | "download" | "shield" | "book" | "idea" | "network" | "layers" | "insight" | "down" | "play" | "skip" | "reset" | "mic" | "back" | "chevron-down" | "timer";
type ActionIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: ActionName;
  size?: number;
};

/** Orin's own compact action glyphs, with a shared stroke and optical size. */
export function ActionIcon({ name, size = 18, ...props }: ActionIconProps) {
  const glyphs = {
    add: <path d="M12 5v14M5 12h14" />,
    timer: <><circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2h6M12 2v3"/></>,
    mic: <><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4m-4 0h8"/></>,
    back: <><path d="m11 5-7 7 7 7M4 12h16"/></>,
    "chevron-down": <path d="m5 9 7 7 7-7"/>,
    play: <path d="m8 5 11 7-11 7z"/>,
    skip: <><path d="m4 5 10 7-10 7zM19 5v14"/></>,
    reset: <><path d="M4 8V4m0 4h4"/><path d="M4.5 8A8.5 8.5 0 1 1 3.5 13"/></>,
    book: <><path d="M12 6c-2-1.5-4.5-2-8-1.5v14c3.5-.5 6 0 8 1.5 2-1.5 4.5-2 8-1.5v-14c-3.5-.5-6 0-8 1.5zM12 6v14"/></>,
    idea: <><path d="M9 17h6m-5 3h4"/><path d="M9 15c0-2-4-3.5-4-7a7 7 0 0 1 14 0c0 3.5-4 5-4 7z"/></>,
    network: <><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="m11 7-5 10m7-10 5 10M7 19h10"/></>,
    layers: <><path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/></>,
    insight: <><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2M8 17h8"/></>,
    left: <path d="m15 5-7 7 7 7"/>,
    right: <path d="m9 5 7 7-7 7"/>,
    filters: <><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="var(--surface, white)"/><circle cx="15" cy="12" r="2" fill="var(--surface, white)"/><circle cx="9" cy="18" r="2" fill="var(--surface, white)"/></>,
    edit: <><path d="M5 19h14M6 15l9-9 3 3-9 9H6z"/><path d="m13.5 7.5 3 3"/></>,
    document: <><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6m-6 4h6"/></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></>,
    shield: <><path d="M12 2.5 20 6v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0v5l-2 3h16l-2-3z"/><path d="M10 19a2 2 0 0 0 4 0"/></>,
    check: <path d="m5 12 4.5 4.5L19 7"/>,
    up: <><path d="m6 12 6-6 6 6M12 6v13"/></>,
    down: <><path d="m6 12 6 6 6-6M12 5v13"/></>,
    external: <><path d="M5 19 19 5M9 5h10v10"/></>,
    command: <><path d="M9 7V5a2 2 0 1 0-2 2h10a2 2 0 1 0-2-2v14a2 2 0 1 0 2-2H7a2 2 0 1 0 2 2z"/></>,
    moon: <path d="M19.5 15.5A8.5 8.5 0 0 1 8.5 4.5 8.5 8.5 0 1 0 19.5 15.5z"/>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4m0-14.2-1.4 1.4M6.3 17.7l-1.4 1.4"/></>,
    history: <><path d="M4 8V4m0 4h4"/><path d="M4.5 8A8.5 8.5 0 1 1 3.5 13"/><path d="M12 7v5l3.5 2"/></>,
    "list-add": <><path d="M4 6h12M4 12h9M4 18h9m5-5v8m-4-4h8"/></>,
    more: <><circle cx="5" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.3" fill="currentColor" stroke="none"/></>,
    logout: <><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/><path d="M13 8l4 4-4 4m4-4H8"/></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></>,
    message: <path d="M5 4.5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 3v-15a2 2 0 0 1 2-2z"/>,
    attachment: <path d="m9 12.5 5.5-5.5a3 3 0 0 1 4.2 4.2l-8 8a5 5 0 0 1-7.1-7.1l8.5-8.5"/>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    pin: <><path d="M9 3.5h6l-.8 6 2.8 3v1.5H7v-1.5l2.8-3z"/><path d="M12 14v7"/></>,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="2" fill="var(--surface, white)" /><circle cx="15" cy="17" r="2" fill="var(--surface, white)" /></>,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {glyphs[name]}
    </svg>
  );
}
