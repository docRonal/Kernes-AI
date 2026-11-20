import { money, moneyParts } from "../format";
import { useCountUp } from "../hooks";

type Props = {
  minor: number;
  tone?: "neg" | "ok" | "scn";
  /** Roll the number in from `from` (defaults to 0). */
  count?: boolean;
  from?: number;
};

/** A money amount set like print: small currency, big złoty, raised grosz. */
export function Figure({ minor, tone, count = false, from = 0 }: Props) {
  const shown = useCountUp(minor, { enabled: count, from });
  const { sign, int, dec } = moneyParts(shown);
  return (
    <span className={tone ? `figure ${tone}` : "figure"}>
      <span className="sr-only">{money(minor)}</span>
      <span aria-hidden="true">
        {sign}
        <span className="cur">PLN</span>
        {int}
        <span className="dec">.{dec}</span>
      </span>
    </span>
  );
}
