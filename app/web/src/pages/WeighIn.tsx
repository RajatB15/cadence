import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { CheckCircle2, Scale as ScaleIcon, Search, Wifi } from "lucide-react";
import { motion } from "motion/react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { CountUp } from "../components/CountUp";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";

const kg = (v: number) => v.toFixed(2);

export function WeighInPage() {
  const openedAt = useRef(new Date().toISOString()).current;
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["scale-status"], queryFn: api.scaleStatus, refetchInterval: 1000 });
  const enable = useMutation({
    mutationFn: () => api.setScale(true),
    onSuccess: () => client.invalidateQueries({ queryKey: ["scale-status"] }),
  });

  return (
    <>
      <PageHeader eyebrow="Local · Bluetooth · no app needed" title={<>Step on and <em className="text-gold">weigh in.</em></>} />
      {q.isPending ? (
        <LoadingBlock height={420} />
      ) : q.isError ? (
        <ErrorBlock error={q.error} retry={() => q.refetch()} />
      ) : (
        <Body s={q.data} openedAt={openedAt} onEnable={() => enable.mutate()} enabling={enable.isPending} />
      )}
    </>
  );
}

function Body({ s, openedAt, onEnable, enabling }: { s: ReturnType<typeof api.scaleStatus> extends Promise<infer T> ? T : never; openedAt: string; onEnable: () => void; enabling: boolean }) {
  const justAccepted = s.last_reading != null && s.last_reading.accepted_at > openedAt;

  if (!s.available) {
    return (
      <Panel icon={ScaleIcon} tone="dim" title="Not set up on this Mac">
        <p>Install the research package alongside the backend to turn this on — see the README's "Using the scale in the app" section.</p>
      </Panel>
    );
  }
  if (!s.enabled) {
    return (
      <Panel icon={ScaleIcon} tone="gold" title="Turn the scale bridge on">
        <p className="mb-5">It listens in the background from here on — this page is just a live view of what's already happening.</p>
        <button type="button" className="pop pop-lime" disabled={enabling} onClick={onEnable}>
          {enabling ? "Turning on…" : "Turn on"}
        </button>
      </Panel>
    );
  }
  if (justAccepted && s.last_reading) {
    return (
      <Panel icon={CheckCircle2} tone="lime" title="Recorded">
        <p className="num text-7xl text-lime">
          <CountUp value={s.last_reading.weight_kg} format={kg} immediate /> <span className="text-2xl text-mute">kg</span>
        </p>
        <p className="mt-4 text-mute">Saved to your weight trend for {s.last_reading.local_date}.</p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link to="/weight" className="pop pop-lime">See your trend</Link>
          <WeighAgainHint />
        </div>
      </Panel>
    );
  }
  if (s.connected && s.live) {
    return (
      <Panel icon={ScaleIcon} tone={s.live.stable ? "lime" : "gold"} title={s.live.stable ? "Locking in…" : "Reading…"} pulse={!s.live.stable}>
        <p className="num text-7xl" style={{ color: s.live.stable ? "#c8f560" : "#d9b26a" }}>
          <CountUp value={s.live.weight_kg} format={kg} immediate /> <span className="text-2xl text-mute">kg</span>
        </p>
        <p className="mt-4 text-mute">{s.live.stable ? "Hold still — saving in a moment." : "Stand still while it settles."}</p>
      </Panel>
    );
  }
  if (s.connected) {
    return (
      <Panel icon={Wifi} tone="gold" title="Connected" pulse>
        <p>Step on the scale now.</p>
      </Panel>
    );
  }
  return (
    <Panel icon={Search} tone="dim" title="Searching for your scale…" pulse>
      <p>Step on it (or tap it awake) — this page updates the moment it connects.</p>
      {s.last_error && <p className="mt-3 text-xs text-coral">Last error: {s.last_error}</p>}
    </Panel>
  );
}

function WeighAgainHint() {
  return <p className="self-center text-xs text-dim">Step off, then on again any time to log another reading.</p>;
}

const TONE: Record<string, string> = { dim: "#8d8a82", gold: "#d9b26a", lime: "#c8f560" };

function Panel({ icon: Icon, tone, title, pulse, children }: { icon: typeof ScaleIcon; tone: "dim" | "gold" | "lime"; title: string; pulse?: boolean; children: React.ReactNode }) {
  const color = TONE[tone];
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="surface flex flex-col items-center p-10 text-center sm:p-16">
      <motion.div
        className="mb-6 grid h-20 w-20 place-items-center rounded-full border"
        style={{ borderColor: `${color}66`, background: `${color}14` }}
        animate={pulse ? { scale: [1, 1.08, 1] } : undefined}
        transition={pulse ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : undefined}
      >
        <Icon size={32} style={{ color }} />
      </motion.div>
      <h2 className={clsx("font-display text-3xl text-cream")}>{title}</h2>
      <div className="mt-2 max-w-md text-mute">{children}</div>
    </motion.section>
  );
}
