import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "default" | "outline" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variants: Record<ButtonVariant, string> = {
  default: "bg-emerald-200 text-[#102019] hover:bg-emerald-100",
  outline: "border border-white/15 bg-transparent text-white hover:bg-white/10",
  ghost: "bg-transparent text-white/80 hover:bg-white/10",
};

export function Button({ className, variant = "default", type = "button", ...props }: ButtonProps) {
  const classes = [
    "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 disabled:pointer-events-none disabled:opacity-50",
    variants[variant],
    className,
  ].filter(Boolean).join(" ");

  return <button className={classes} type={type} {...props} />;
}
