import type { SVGProps } from "react";

type ActionName = "add" | "close" | "settings";
type ActionIconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: ActionName;
  size?: number;
};

/** Orin's own compact action glyphs, with a shared stroke and optical size. */
export function ActionIcon({ name, size = 18, ...props }: ActionIconProps) {
  const glyphs = {
    add: <path d="M12 5v14M5 12h14" />,
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
