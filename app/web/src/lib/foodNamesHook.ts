/**
 * React side of "my name": the shared dish list (with your queued edits on top), and add / remove / prefer with an optimistic
 * update, a retry queue for offline use, and a flush when the connection or the app comes back.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { applyPending, createNameQueue, localNameStore, newAddOp, withMyName, withoutMyName, withPreferred, type NameOp } from "./foodNames";
import { isRetryable } from "./foodOutbox";
import type { FoodDish } from "./types";

const send = async (op: NameOp): Promise<void> => {
  if (op.kind === "add") await api.addDishName(op.dish_id, op.name, op.preferred, op.key);
  else if (op.kind === "remove") await api.deleteDishName(op.dish_id, op.alias_id);
  else await api.setDishNamePreferred(op.dish_id, op.alias_id, op.preferred);
};

export const nameQueue = createNameQueue(localNameStore(), send, isRetryable, (e) => e instanceof ApiError && e.status === 409);

const KEY = ["food-dishes"] as const;

/** Re-renders when the queue changes. */
function useQueued(): NameOp[] {
  const [ops, setOps] = useState<NameOp[]>(() => nameQueue.list());
  useEffect(() => nameQueue.subscribe(() => setOps(nameQueue.list())), []);
  return ops;
}

/** The dish list used everywhere in Food: one cache entry, your queued name edits applied. */
export function useFoodDishes() {
  const ops = useQueued();
  const client = useQueryClient();
  const select = useMemo(() => (d: { dishes: FoodDish[] }) => ({ ...d, dishes: ops.length ? applyPending(d.dishes ?? [], ops) : d.dishes ?? [] }), [ops]);
  const query = useQuery({ queryKey: KEY, queryFn: api.foodDishes, staleTime: 10 * 60_000, select });
  useEffect(() => {
    const go = () => void nameQueue.flush().then((r) => { if (r.sent) void client.invalidateQueries({ queryKey: KEY }); });
    const onVisible = () => { if (document.visibilityState === "visible") go(); };
    if (nameQueue.list().length) go();
    window.addEventListener("online", go);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("online", go);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [client]);
  return { ...query, waiting: ops.filter((o) => o.status === "queued").length, needLook: ops.filter((o) => o.status === "needs_look") };
}

type Patch = (all: FoodDish[]) => FoodDish[];

export function useMyNames() {
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: async ({ op }: { op: NameOp; patch: Patch }) => nameQueue.submit(op),
    onMutate: async ({ patch }) => {
      await client.cancelQueries({ queryKey: KEY });
      const before = client.getQueryData<{ dishes: FoodDish[] }>(KEY);
      if (before) client.setQueryData(KEY, { ...before, dishes: patch(before.dishes) });
      return { before };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.before) client.setQueryData(KEY, ctx.before);
    },
    onSuccess: (status) => {
      if (status === "sent") void client.invalidateQueries({ queryKey: KEY });
    },
  });
  return {
    /** Resolves "sent" or "queued" (saved on this phone, will sync). Rejects with the server's message on a refusal. */
    add: (dishId: number, name: string, preferred: boolean) => {
      const op = newAddOp(dishId, name, preferred);
      return run.mutateAsync({ op, patch: (all) => withMyName(all, dishId, name, preferred, op.local_id) });
    },
    remove: (dishId: number, aliasId: number) =>
      run.mutateAsync({ op: { key: `rm:${dishId}:${aliasId}`, kind: "remove", dish_id: dishId, alias_id: aliasId, created_at: Date.now(), attempts: 0, status: "queued" }, patch: (all) => withoutMyName(all, dishId, aliasId) }),
    prefer: (dishId: number, aliasId: number, preferred: boolean) =>
      run.mutateAsync({ op: { key: `pf:${dishId}:${aliasId}:${preferred}`, kind: "prefer", dish_id: dishId, alias_id: aliasId, preferred, created_at: Date.now(), attempts: 0, status: "queued" }, patch: (all) => withPreferred(all, dishId, aliasId, preferred) }),
    pending: run.isPending,
  };
}
