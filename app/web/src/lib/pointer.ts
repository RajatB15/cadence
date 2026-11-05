/** True on devices with a precise pointer (mouse/trackpad). Autofocus on touch devices pops the keyboard and scrolls the page. */
export function hasFinePointer(win: Pick<Window, "matchMedia"> | undefined = typeof window === "undefined" ? undefined : window): boolean {
  try {
    return win?.matchMedia?.("(pointer: fine)").matches ?? true;
  } catch {
    return true;
  }
}
