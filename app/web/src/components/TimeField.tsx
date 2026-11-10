import { formatTimeDigits } from "../lib/goals";

/**
 * A target-time box that works with a phone's number pad: type only digits and they fill from the right as h:mm:ss
 * (3 4 5 0 0 becomes 3:45:00). Pasting or typing colons also works.
 */
export function TimeField({ id, value, onChange, invalid, className }: { id: string; value: string; onChange: (text: string) => void; invalid?: boolean; className?: string }) {
  return (
    <input
      id={id}
      className={className}
      inputMode="numeric"
      pattern="[0-9:]*"
      autoComplete="off"
      enterKeyHint="done"
      placeholder="h:mm:ss"
      value={value}
      aria-invalid={invalid}
      aria-describedby={`${id}-help`}
      onChange={(e) => onChange(formatTimeDigits(e.target.value))}
    />
  );
}
