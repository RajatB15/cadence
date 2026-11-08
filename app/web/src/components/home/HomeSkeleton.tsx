import { Skeleton } from "../Shell";

/** Home while the first response loads: the same silhouette as the finished page, so nothing jumps when data lands. */
export function HomeSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-busy="true" aria-label="Loading Home">
      <div>
        <Skeleton className="mb-4 h-4 w-40 !rounded-full" />
        <Skeleton className="h-11 w-72 max-w-full" />
      </div>
      <div className="surface p-5 sm:p-7">
        <Skeleton className="mb-5 h-3 w-36 !rounded-full" />
        <div className="grid items-center gap-6 sm:grid-cols-[auto_1fr]">
          <Skeleton className="mx-auto h-[212px] w-[212px] !rounded-full sm:h-[248px] sm:w-[248px]" />
          <div className="grid grid-cols-2 gap-2.5">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[76px] !rounded-2xl" />)}
          </div>
        </div>
      </div>
      <div className="flex gap-3 overflow-hidden">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[112px] w-[132px] shrink-0 !rounded-[22px] sm:w-full" />)}
      </div>
      <Skeleton className="h-40 !rounded-[22px]" />
    </div>
  );
}
