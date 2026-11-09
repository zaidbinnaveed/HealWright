import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

type Variant = "primary" | "secondary" | "danger";

const BASE =
  "relative inline-flex cursor-pointer items-center justify-center gap-2 overflow-hidden rounded-full px-4 py-2 text-sm font-semibold tracking-tight transition duration-300 disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT: Record<Variant, string> = {
  primary: "bg-ink text-bg shadow-md hover:enabled:scale-[1.04] aria-disabled:opacity-50",
  secondary:
    "border border-line-strong bg-surface text-ink shadow-sm hover:shadow active:enabled:scale-95",
  danger: "bg-red-600 text-white shadow-md hover:enabled:scale-[1.04]",
};

function Overlay({ variant }: { variant: Variant }) {
  return variant === "secondary" ? (
    <span
      aria-hidden="true"
      className="absolute inset-0 rounded-full bg-ink opacity-0 transition-opacity duration-100 ease-linear hover:opacity-[0.06]"
    />
  ) : null;
}

export function Button({
  variant = "primary",
  icon,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: ReactNode }) {
  return (
    <button type="button" {...rest} className={`${BASE} ${VARIANT[variant]} ${className}`}>
      {icon}
      <span>{children}</span>
      <Overlay variant={variant} />
    </button>
  );
}

export function ButtonLink({
  variant = "primary",
  icon,
  className = "",
  children,
  ...rest
}: LinkProps & { variant?: Variant; icon?: ReactNode }) {
  return (
    <Link {...rest} className={`${BASE} ${VARIANT[variant]} ${className}`}>
      {icon}
      <span>{children}</span>
      <Overlay variant={variant} />
    </Link>
  );
}

export function SendIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg aria-hidden="true" className={`rotate-45 ${className}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  );
}
