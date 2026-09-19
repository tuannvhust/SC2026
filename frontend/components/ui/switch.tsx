type SwitchProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

export function Switch({ checked, onCheckedChange }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition ${checked ? "bg-blue-600" : "bg-slate-300 dark:bg-slate-700"}`}
    >
      <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${checked ? "left-6" : "left-1"}`} />
    </button>
  );
}
