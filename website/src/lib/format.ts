export function fmtScore(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined) return "n/a";
  if (n === 1) return "1.0";
  if (n === 0) return "0";
  const s = n.toFixed(digits);
  return s.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

export function frac(found: number, total: number): string {
  return `${found}/${total}`;
}
