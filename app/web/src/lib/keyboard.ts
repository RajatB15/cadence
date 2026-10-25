import { useEffect, useState } from "react";

/** How much of the layout viewport the on-screen keyboard covers, and the height left above it (iOS does not resize the page for the keyboard). */
export function keyboardInset(layoutHeight: number, visualHeight: number, visualTop: number): number {
  const covered = layoutHeight - visualHeight - visualTop;
  return covered > 80 ? Math.round(covered) : 0; // small differences are browser chrome, not a keyboard
}

export function useKeyboardInset(active: boolean): { inset: number; visibleHeight: number | null } {
  const [state, setState] = useState<{ inset: number; visibleHeight: number | null }>({ inset: 0, visibleHeight: null });
  useEffect(() => {
    const vv = typeof window !== "undefined" ? window.visualViewport : null;
    if (!active || !vv) return;
    const update = () => {
      const inset = keyboardInset(window.innerHeight, vv.height, vv.offsetTop);
      setState((s) => (s.inset === inset && s.visibleHeight === vv.height ? s : { inset, visibleHeight: vv.height }));
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      setState({ inset: 0, visibleHeight: null });
    };
  }, [active]);
  return state;
}
