import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-navy-900 text-white shadow-sm hover:bg-navy-800 active:bg-navy-950",
  secondary:
    "bg-white text-navy-800 border border-navy-200 shadow-sm hover:border-navy-300 hover:bg-navy-50 active:bg-navy-100",
  ghost: "bg-transparent text-navy-600 hover:bg-navy-100 hover:text-navy-900",
  danger: "bg-danger text-white shadow-sm hover:opacity-90 active:opacity-100",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-medium transition-all duration-150 ease-out",
          "focus-visible:outline-none focus-visible:shadow-focus-ring",
          "active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100",
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
