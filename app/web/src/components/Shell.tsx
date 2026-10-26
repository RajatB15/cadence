import * as Tooltip from "@radix-ui/react-tooltip";
import { clsx } from "clsx";
import { Activity, Archive, BookOpen, CalendarCheck, FlaskConical, Flag, Flame, Gauge, LayoutGrid, Scale, Settings2, Utensils } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { RefreshRailButton } from "./RefreshButton";
import { ReminderBanner } from "./ReminderBanner";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid },
  { to: "/coach", label: "Coach", icon: Gauge },
  { to: "/plan", label: "Plan", icon: CalendarCheck },
  { to: "/weight", label: "Weight", icon: Scale },
  { to: "/activities", label: "Activities", icon: Activity },
  // The phone tab bar has room for six: Food opens from a chip on Overview, Goals and the Lab open from Plan and Coach, the Vault from Settings.
  { to: "/food", label: "Food", icon: Utensils, desktopOnly: true },
  { to: "/reading", label: "Reading", icon: BookOpen, desktopOnly: true },
  { to: "/phases", label: "Phases", icon: Flame, desktopOnly: true },
  { to: "/goals", label: "Goals", icon: Flag, desktopOnly: true },
  { to: "/lab", label: "Lab", icon: FlaskConical, desktopOnly: true },
  { to: "/vault", label: "Vault", icon: Archive, desktopOnly: true },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

function Monogram() {
  const reduce = useReducedMotion();
  return (
    <div className="h-11 w-11 rounded-[10px] shadow-[0_8px_18px_-8px_rgba(0,0,0,0.95)]" aria-label="Cadence">
      <svg viewBox="0 0 32 32" className="h-full w-full" aria-hidden>
        <defs>
<radialGradient id="cm-t1" gradientUnits="userSpaceOnUse" cx="8" cy="6" r="15"><stop offset="0" stopColor="#7c6bff" stopOpacity=".75"/><stop offset="1" stopColor="#7c6bff" stopOpacity="0"/>{!reduce && (<><animate attributeName="cx" values="6;26;24;8;6" dur="9s" repeatCount="indefinite"/><animate attributeName="cy" values="6;10;27;24;6" dur="9s" repeatCount="indefinite"/></>)}</radialGradient>
<radialGradient id="cm-t2" gradientUnits="userSpaceOnUse" cx="26" cy="26" r="13"><stop offset="0" stopColor="#3fd0ff" stopOpacity=".6"/><stop offset="1" stopColor="#3fd0ff" stopOpacity="0"/>{!reduce && (<><animate attributeName="cx" values="26;6;8;26;26" dur="11s" repeatCount="indefinite"/><animate attributeName="cy" values="26;24;6;8;26" dur="11s" repeatCount="indefinite"/></>)}</radialGradient>
<radialGradient id="cm-bg" cx="50%" cy="-10%" r="120%"><stop offset="0" stopColor="#30333a"/><stop offset=".45" stopColor="#14151a"/><stop offset="1" stopColor="#020203"/></radialGradient>
<radialGradient id="cm-vg" cx="50%" cy="55%" r="60%"><stop offset=".6" stopColor="#000" stopOpacity="0"/><stop offset="1" stopColor="#000" stopOpacity=".55"/></radialGradient>
<linearGradient id="cm-gl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" stopOpacity=".17"/><stop offset="1" stopColor="#fff" stopOpacity=".01"/></linearGradient>
<linearGradient id="cm-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" stopOpacity=".55"/><stop offset=".4" stopColor="#fff" stopOpacity=".06"/><stop offset="1" stopColor="#fff" stopOpacity=".16"/></linearGradient>
<linearGradient id="cm-core" x1="0" y1="6" x2="0" y2="26" gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#fff"/><stop offset=".55" stopColor="#eef2ff"/><stop offset="1" stopColor="#b9c4e6"/></linearGradient>
<filter id="cm-b1" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.4"/></filter>
<filter id="cm-b2" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation=".9"/></filter>
<linearGradient id="cm-sh" gradientUnits="userSpaceOnUse" x1="-9" y1="0" x2="-1" y2="0"><stop offset="0" stopColor="#fff" stopOpacity="0"/><stop offset=".5" stopColor="#fff" stopOpacity="1"/><stop offset="1" stopColor="#fff" stopOpacity="0"/>{!reduce && (<animateTransform attributeName="gradientTransform" type="translate" values="-4 0;44 0;44 0" keyTimes="0;.42;1" dur="3.4s" repeatCount="indefinite" calcMode="spline" keySplines=".45 0 .25 1;0 0 1 1"/>)}</linearGradient>
<clipPath id="cm-cp"><path d="M0 7.4Q0 0 7.4 0H24.6Q32 0 32 7.4V12.2Q16 17.6 0 12.2Z"/></clipPath>
</defs><rect width="32" height="32" rx="7.4" fill="url(#cm-bg)"/><rect width="32" height="32" rx="7.4" fill="url(#cm-vg)"/><rect width="32" height="32" rx="7.4" fill="url(#cm-t1)"/><rect width="32" height="32" rx="7.4" fill="url(#cm-t2)"/><g clipPath="url(#cm-cp)"><rect width="32" height="32" fill="url(#cm-gl)"/></g><rect x=".3" y=".3" width="31.4" height="31.4" rx="7.4" fill="none" stroke="url(#cm-rim)" strokeWidth=".6"/><path d="M3.5 17H10L13.5 8L18.5 24.5L21.5 17H28.5" stroke="#7d9bff" strokeOpacity=".55" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" filter="url(#cm-b1)"/><path d="M3.5 17H10L13.5 8L18.5 24.5L21.5 17H28.5" stroke="#fff" strokeOpacity=".7" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" fill="none" filter="url(#cm-b2)"/><path d="M3.5 17H10L13.5 8L18.5 24.5L21.5 17H28.5" stroke="url(#cm-core)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/><path d="M3.5 17H10L13.5 8L18.5 24.5L21.5 17H28.5" stroke="#fff" strokeWidth=".45" strokeLinecap="round" strokeLinejoin="round" fill="none" transform="translate(-.2 -.6)" opacity=".7"/><path d="M3.5 17H10L13.5 8L18.5 24.5L21.5 17H28.5" stroke="url(#cm-sh)" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
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
          {NAV.filter((item) => !("desktopOnly" in item)).map(({ to, label, icon: Icon }) => (
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
