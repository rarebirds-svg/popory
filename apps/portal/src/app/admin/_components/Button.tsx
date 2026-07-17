// admin 공통 버튼. variant(primary/secondary/danger)와 비활성·포커스 스타일을 표준화한다.
import type { ButtonHTMLAttributes } from "react";

const VARIANT = {
  primary: "bg-popory-accent font-medium text-white",
  secondary: "border border-popory-border text-popory-fg",
  danger: "border border-popory-danger text-popory-danger",
} as const;

export type ButtonVariant = keyof typeof VARIANT;

export function Button({
  variant = "secondary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-popory-accent ${VARIANT[variant]} ${className}`}
      {...rest}
    />
  );
}
