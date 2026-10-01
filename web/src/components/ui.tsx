// Small vendored UI primitives (shadcn-style: Tailwind classes, no runtime library).
import clsx from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "default",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" | "danger"; size?: "sm" | "md" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-1 rounded border whitespace-nowrap transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
        size === "sm" ? "h-5 px-1.5 text-[11px]" : "h-6 px-2",
        variant === "default" && "border-line bg-bg3 hover:border-accent2",
        variant === "primary" && "border-accent bg-accent text-white hover:brightness-110",
        variant === "ghost" && "border-transparent hover:bg-bg3",
        variant === "danger" && "border-err text-err hover:bg-err hover:text-white",
        className,
      )}
    />
  );
}

export function IconButton({
  active,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex h-6 w-6 items-center justify-center rounded hover:bg-bg3 disabled:opacity-40",
        active && "bg-bg3 text-accent",
        className,
      )}
    />
  );
}

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: "neutral" | "warn" | "ok" | "err" | "info";
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center rounded px-1 py-px text-[10px] font-medium leading-tight",
        tone === "neutral" && "bg-bg3 text-dim",
        tone === "warn" && "bg-warn/20 text-warn",
        tone === "ok" && "bg-ok/20 text-ok",
        tone === "err" && "bg-err/20 text-err",
        tone === "info" && "bg-accent2/20 text-accent2",
      )}
    >
      {children}
    </span>
  );
}

/** Shown on anything backed by an unverified component spec. */
export function Unverified({ source }: { source?: string }) {
  return (
    <Badge tone="warn" title={`Unverified spec. Check it against the source before relying on it.${source ? "\nSource: " + source : ""}`}>
      unverified
    </Badge>
  );
}

export function Planned() {
  return (
    <Badge tone="info" title="Scaffolded for a later phase: the interface exists, the behaviour does not yet.">
      planned
    </Badge>
  );
}

export function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-b border-line">
      <header className="flex h-6 items-center justify-between bg-bg px-2 text-[11px] font-semibold uppercase tracking-wide text-dim">
        <span>{title}</span>
        {right}
      </header>
      <div className="p-2">{children}</div>
    </section>
  );
}

/** Empty states teach: say what the panel is for and the one action that fills it. */
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-dim">
      <div className="text-[13px] font-semibold text-fg">{title}</div>
      {children && <div className="max-w-sm leading-relaxed">{children}</div>}
      {action}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line bg-bg px-1 font-mono text-[10px]">{children}</kbd>;
}

export function PanelScroll({ children, className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={clsx("h-full overflow-auto", className)}>
      {children}
    </div>
  );
}

export function Row({ label, children, title }: { label: ReactNode; children: ReactNode; title?: string }) {
  return (
    <div className="flex min-h-6 items-center gap-2 py-px" title={title}>
      <div className="w-[42%] shrink-0 truncate text-dim">{label}</div>
      <div className="flex min-w-0 flex-1 items-center gap-1">{children}</div>
    </div>
  );
}

export function fmt(value: unknown, digits = 2): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "-";
    return Number.isInteger(value) ? String(value) : value.toFixed(digits);
  }
  return String(value);
}
