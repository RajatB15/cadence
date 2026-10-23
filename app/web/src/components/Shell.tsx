import * as Tooltip from "@radix-ui/react-tooltip";
import { clsx } from "clsx";
import { Activity, Archive, Gauge, LayoutGrid, Scale, Settings2 } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { RefreshRailButton } from "./RefreshButton";
import { ReminderBanner } from "./ReminderBanner";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid },
  { to: "/coach", label: "Coach", icon: Gauge },
  { to: "/weight", label: "Weight", icon: Scale },
  { to: "/activities", label: "Activities", icon: Activity },
  { to: "/vault", label: "Vault", icon: Archive },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

function Monogram() {
  return (
    <div className="grid h-11 w-11 place-items-center bg-cream text-ink" aria-label="Cadence">
      <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
        <path d="M3 17 H10 L13 9 L18 24 L21 17 H29" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" fill="none" />
      </svg>
    </div>
  );
}

function RailLink({ to, label, icon: Icon }: (typeof NAV)[number]) {
  // Radix asChild stringifies function classNames, so derive the active state here.
  const isActive = useMatch({ path: to, end: to === "/" }) != null;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <NavLink
          to={to}
          end={to === "/"}
          aria-label={label}
          className={clsx(
            "relative grid h-12 w-12 place-items-center transition-colors",
            isActive ? "text-ink" : "text-mute hover:text-paper",
          )}
        >
          {isActive && (
            <motion.span
              layoutId="nav-active"
              className="absolute inset-0 bg-cream"
              transition={{ type: "spring", stiffness: 500, damping: 38 }}
            />
          )}
          <Icon size={20} strokeWidth={1.75} className="relative" />
        </NavLink>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="right"
          sideOffset={14}
          className="z-50 border border-line-strong bg-coal px-3 py-1.5 text-xs font-semibold tracking-widest text-paper uppercase"
        >
          {label}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Shell() {
  const location = useLocation();
  return (
    <Tooltip.Provider delayDuration={150}>
      <div className="min-h-dvh md:pl-24">
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-24 flex-col items-center border-r border-line bg-ink/80 py-7 backdrop-blur md:flex">
          <Monogram />
          <nav className="mt-14 flex flex-col gap-3" aria-label="Primary">
            {NAV.map((item) => (
              <RailLink key={item.to} {...item} />
            ))}
          </nav>
          <div className="mt-6 border-t border-line pt-6">
            <RefreshRailButton />
          </div>
          <div className="mt-auto eyebrow [writing-mode:vertical-rl] rotate-180 !text-dim">Local · Private</div>
        </aside>

        <main className="mx-auto max-w-[1280px] px-5 pt-8 pb-32 sm:px-8 md:pt-12 lg:px-12">
          <ReminderBanner />
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.2, 0.9, 0.1, 1] }}
          >
            <Outlet />
          </motion.div>
        </main>

        <nav
          aria-label="Primary"
          className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-line bg-ink/90 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
        >
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex min-w-0 flex-col items-center gap-1 py-3 text-[10.5px] font-semibold",
                  isActive ? "text-cream" : "text-dim",
                )
              }
            >
              <Icon size={20} strokeWidth={1.75} />
              <span className="max-w-full truncate px-0.5">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </Tooltip.Provider>
  );
}

export function PageHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-6">
      <div>
        <div className="eyebrow mb-3 flex flex-wrap items-center gap-3">{eyebrow}</div>
        <h1 className="font-display text-5xl leading-[0.95] tracking-tight text-cream sm:text-6xl lg:text-7xl">
          {title}
        </h1>
      </div>
      {children && <div className="flex flex-wrap items-center gap-4">{children}</div>}
    </header>
  );
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex border border-line-strong p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={clsx(
              "relative px-3.5 py-1.5 text-xs font-semibold tracking-widest uppercase transition-colors pointer-coarse:py-2.5",
              active ? "text-ink" : "text-mute hover:text-paper",
            )}
          >
            {active && (
              <motion.span
                layoutId={`seg-${label}`}
                className="absolute inset-0 bg-cream"
                transition={{ type: "spring", stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function DemoChip() {
  return (
    <span className="chip !border-gold/40 !text-gold" title="Synthetic data generated locally">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gold" />
      Demo data
    </span>
  );
}

export function LoadingBlock({ height = 240 }: { height?: number }) {
  return (
    <div
      className="surface animate-pulse"
      style={{ height }}
      aria-busy="true"
      aria-label="Loading"
    />
  );
}

export function ErrorBlock({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className="surface flex flex-wrap items-center justify-between gap-4 border-coral/40 p-6">
      <div>
        <p className="font-semibold text-coral">Couldn't load this view</p>
        <p className="text-sm text-mute">
          {message}. Make sure the local Cadence service is running.
        </p>
      </div>
      {retry && (
        <button type="button" className="pop pop-ghost" onClick={retry}>
          Retry
        </button>
      )}
    </div>
  );
}
