import type { SVGProps } from "react";

type ActionName = "add" | "close" | "settings" | "menu" | "pin" | "logout" | "copy" | "search" | "message" | "attachment";
type ActionIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: ActionName;
  size?: number;
};

/** Orin's own compact action glyphs, with a shared stroke and optical size. */
export function ActionIcon({ name, size = 18, ...props }: ActionIconProps) {
  const glyphs = {
    add: <path d="M12 5v14M5 12h14" />,
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
