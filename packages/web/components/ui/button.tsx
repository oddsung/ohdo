import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-gray-900 text-white hover:bg-gray-800 disabled:bg-gray-400",
  secondary:
    "bg-white text-gray-900 border border-gray-300 hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400",
  ghost:
    "bg-transparent text-gray-600 hover:bg-gray-100 disabled:text-gray-300",
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "primary", className = "", ...rest },
  ref,
) {
  const base =
    "inline-flex items-center justify-center px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:cursor-not-allowed";
  return (
    <button
      ref={ref}
      {...rest}
      className={`${base} ${VARIANT_CLASSES[variant]} ${className}`.trim()}
    />
  );
});
