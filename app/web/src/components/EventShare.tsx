import { useQuery } from "@tanstack/react-query";
import { Share2 } from "lucide-react";
import { useState } from "react";
import { READ_ONLY, api } from "../lib/api";
import { buildEventCardModel } from "../lib/eventCard";
import type { ActivityDetail, EventDetail } from "../lib/types";
import { ShareBody } from "./ShareCard";
import { Sheet } from "./Sheet";

/** Share the whole event: one card (and, with GPS, one flyover video) for the joined route and the event's totals. */
export function ShareEventButton({ event }: { event: EventDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="pop pop-ghost inline-flex items-center gap-2" onClick={() => setOpen(true)}>
        <Share2 size={14} /> Share
      </button>
      <Sheet open={open} onOpenChange={setOpen} eyebrow="Share" title="Event card">
        <EventShareBody event={event} />
      </Sheet>
    </>
  );
}

const ids = (e: EventDetail) => e.days.flatMap((d) => d.activities.map((a) => a.id));

function EventShareBody({ event }: { event: EventDetail }) {
  const [progress, setProgress] = useState(0);
  const all = ids(event);
  const query = useQuery({
    queryKey: ["event-share", event.id, all.join(",")],
    // One at a time: any recording not archived yet is downloaded (once, then kept in the vault) at the sync's polite pace.
    queryFn: async (): Promise<ActivityDetail[]> => {
      const out: ActivityDetail[] = [];
      for (const [i, id] of all.entries()) {
        let d = await api.activity(id);
        if (!READ_ONLY && d.activity.source_id === "garmin" && d.missing.includes("activity_fit")) {
          try {
            await api.fetchActivity(id);
            d = await api.activity(id);
          } catch {
            // Keep what we have: this recording just won't add to the route.
          }
        }
        out.push(d);
        setProgress(i + 1);
      }
      return out;
    },
    staleTime: 0,
    gcTime: 0,
  });

  if (query.isPending) {
    return <p className="text-sm text-mute">Gathering the routes… {progress} of {all.length} recordings (any not yet archived are downloaded from Garmin once).</p>;
  }
  if (query.isError) return <p role="alert" className="text-sm text-coral">Couldn't load the recordings: {query.error.message}</p>;

  const model = buildEventCardModel(event, query.data);
  const routed = query.data.filter((d) => d.fit && !d.fit.error && d.fit.route.length > 1).length;
  return (
    <div className="space-y-6">
      {routed < all.length && (
        <p className="text-xs text-gold">
          {routed === 0
            ? "None of these recordings has GPS in the vault, so the card shows the totals and the days without a map."
            : `The route joins ${routed} of ${all.length} recordings; the others have no GPS in the vault. Totals include all of them.`}
        </p>
      )}
      <ShareBody model={model} />
    </div>
  );
}
