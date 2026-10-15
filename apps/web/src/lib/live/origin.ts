/**
 * The rule of a run's origin as the page shows it, with the seed of a sample. The API writes the
 * seed as the rule's last sentence ("Seed N: the same seed repeats this pick.") and keeps the rule
 * within 600 characters by cutting after a whole sentence and adding an ellipsis, which for a
 * sample is usually the seed sentence. The page then writes the seed itself, so the ellipsis
 * after the full stop goes: what remains is whole sentences, and the seed follows them.
 */
export function originRule(
  rule: string,
  seed: number | null | undefined,
): { rule: string; seed: string | null } {
  if (seed == null || rule.includes(`Seed ${seed}`)) return { rule, seed: null };
  return {
    rule: rule.replace(/([.!?])\s*…$/u, "$1"),
    seed: `Seed ${seed}: the same seed repeats this pick.`,
  };
}
