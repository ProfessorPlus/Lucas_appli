import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency: string): string {
  const code = currency.toUpperCase();
  const formatter = new Intl.NumberFormat("fr-FR", {
    style: "decimal",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatter.format(amount)} ${code}`;
}

export function currencySymbol(currency: string): string {
  const c = currency.toUpperCase();
  if (c === "EUR") return "€";
  if (c === "CHF") return "CHF";
  if (c === "AED") return "AED";
  if (c === "USD") return "$";
  return c;
}
