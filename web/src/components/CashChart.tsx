import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { groupByDate, niceTicks, type Facts } from "../analysis";
import {
  axisLabel,
  dayOfMonth,
  fullDate,
  isWeekend,
  longDate,
  money,
  moneyShort,
  truncate,
  weekday,
} from "../format";
import { useElementWidth } from "../hooks";
import type { ForecastResponse, Scenario } from "../types";

type Props = {
  forecast: ForecastResponse;
  facts: Facts;
  scenario: Scenario | null;
  /** Credit line the user approved in the simulation, 0 otherwise. */
  coveredMinor: number;
};

const spring = { type: "spring", stiffness: 170, damping: 24 } as const;

export function ChartBlock(props: Props) {
  const { forecast, scenario, coveredMinor } = props;
  const days = forecast.baseline.days;
  const scenarioDays = scenario?.projection.days;

  const legend: [string, string][] = [
    ["sw-bal", "End-of-day balance"],
    ["sw-neg", "Below zero"],
  ];
  if (coveredMinor) legend.push(["sw-cov", "Covered by the credit line (simulated)"]);
  if (scenario) legend.push(["sw-scn", "What-if"]);
  legend.push(["sw-wkd", "Weekend"]);

  return (
    <section className="chart-block" aria-labelledby="chart-title">
      <div className="chart-head">
        <h3 id="chart-title" className="chart-title">
          Balance at the end of each day
          <span>
            {fullDate(days[0].date)} – {fullDate(days[days.length - 1].date)}
          </span>
        </h3>
        <ul className="legend">
          {legend.map(([swatch, text]) => (
            <li key={swatch}>
              <span className={`sw ${swatch}`} aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      </div>

      <CashChart {...props} />

      <details className="numbers">
        <summary>See the numbers</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">End-of-day balance</th>
                {scenarioDays && <th scope="col">What-if</th>}
              </tr>
            </thead>
            <tbody>
              {days.map((day, index) => (
                <tr key={day.date}>
                  <td>{longDate(day.date)}</td>
                  <td className={day.balance_minor < 0 ? "neg" : undefined}>{money(day.balance_minor)}</td>
                  {scenarioDays && (
                    <td className={scenarioDays[index].balance_minor < 0 ? "neg" : "scn"}>
                      {money(scenarioDays[index].balance_minor)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function CashChart({ forecast, facts, scenario, coveredMinor }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const days = forecast.baseline.days;
  const scenarioDays = scenario?.projection.days ?? null;
  const events = useMemo(() => groupByDate(forecast.transactions), [forecast]);
  const narrow = width > 0 && width < 640;
  const height = narrow ? 300 : 390;

  const geometry = useMemo(() => {
    if (!width) return null;
    const margin = { top: narrow ? 50 : 78, right: 6, bottom: 50, left: narrow ? 40 : 58 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const values = [...days, ...(scenarioDays ?? [])].map((day) => day.balance_minor);
    if (coveredMinor) values.push(-coveredMinor);
    const ticks = niceTicks(Math.min(...values), Math.max(...values), narrow ? 4 : 5);
    const low = ticks[0];
    const high = ticks[ticks.length - 1];
    const y = (value: number) => margin.top + ((high - value) / (high - low)) * plotHeight;
    const column = plotWidth / days.length;
    const left = (index: number) => margin.left + column * index;
    const center = (index: number) => left(index) + column / 2;
    const barWidth = Math.max(6, Math.min(46, column * (narrow ? 0.62 : 0.52)));
    return { margin, plotWidth, plotHeight, ticks, y, zero: y(0), column, left, center, barWidth };
  }, [width, narrow, height, days, scenarioDays, coveredMinor]);

  if (!geometry) return <div ref={ref} className="chart-stage" style={{ height }} />;

  const { margin, plotWidth, plotHeight, ticks, y, zero, column, left, center, barWidth } = geometry;
  const last = days.length - 1;
  const eventY = margin.top - 16;
  const movedIndex = scenario ? days.findIndex((day) => day.date === scenario.move.date) : -1;
  const movedTransaction = scenario ? forecast.transactions.find((t) => t.id === scenario.move.id) : undefined;

  // Event labels may spread towards empty neighbouring columns instead of being cut at one column.
  const markers = days
    .map((day, index) => (events.has(day.date) || index === movedIndex ? index : -1))
    .filter((index) => index >= 0);
  const labelRoom = (index: number) => {
    const gaps = markers.filter((other) => other !== index).map((other) => Math.abs(other - index));
    const neighbour = gaps.length ? Math.min(...gaps) : days.length;
    const edge = Math.min(index + 0.5, days.length - index - 0.5) * 2;
    return Math.floor((Math.min(neighbour, edge, 3) * column - 4) / 6.6);
  };
  const amountY = (index: number, text: string) =>
    labelRoom(index) < text.length && markers.indexOf(index) % 2 === 1 ? eventY - 26 : eventY - 12;

  const labelled = new Set(
    (narrow ? [facts.firstIndex, facts.deepestIndex] : [0, facts.firstIndex, facts.deepestIndex, last]).filter(
      (index) => index >= 0,
    ),
  );

  const scenarioPath = scenarioDays
    ?.map((day, index) => {
      const start = index === 0 ? `M ${left(0) + 4} ${y(day.balance_minor)}` : `V ${y(day.balance_minor)}`;
      return `${start} H ${left(index + 1) - (index === last ? 4 : 0)}`;
    })
    .join(" ");
  const firstChange = scenarioDays?.findIndex((day, index) => day.balance_minor !== days[index].balance_minor) ?? -1;

  const summary = facts.first
    ? `Cash balance for 14 days. It goes below zero on ${longDate(facts.first.date)} by ${money(facts.first.shortfall_minor)}.`
    : `Cash balance for 14 days. It stays above zero; the lowest balance is ${money(facts.lowest.balance_minor)}.`;

  const hovered = hover === null ? null : days[hover];

  return (
    <div ref={ref} className="chart-stage" onPointerLeave={() => setHover(null)}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
        <defs>
          <Hatch id="hatch-red" tone="red" />
          <Hatch id="hatch-green" tone="green" />
        </defs>

        {days.map((day, index) =>
          isWeekend(day.date) ? (
            <rect key={`w-${day.date}`} className="weekend" x={left(index)} y={margin.top} width={column} height={plotHeight} />
          ) : null,
        )}
        {hover !== null && (
          <rect className="hover-col" x={left(hover)} y={margin.top - 4} width={column} height={plotHeight + 8} />
        )}

        {ticks.map((tick) => (
          <g key={`t-${tick}`}>
            {tick !== 0 && <line className="grid" x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} />}
            <text className="axis" x={margin.left - 10} y={y(tick)} dy="0.32em" textAnchor="end">
              {axisLabel(tick)}
            </text>
          </g>
        ))}

        {coveredMinor > 0 && (
          <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}>
            <rect className="band" x={margin.left} y={zero} width={plotWidth} height={y(-coveredMinor) - zero} />
            <line className="band-edge" x1={margin.left} x2={width - margin.right} y1={y(-coveredMinor)} y2={y(-coveredMinor)} />
            {!narrow && (
              <text className="band-label" x={width - margin.right - 6} y={y(-coveredMinor) + 15} textAnchor="end">
                Credit line {moneyShort(coveredMinor)} · simulated
              </text>
            )}
          </motion.g>
        )}

        {days.map((day, index) => {
          const value = day.balance_minor;
          const top = Math.min(y(value), zero);
          const barHeight = Math.max(2, Math.abs(y(value) - zero));
          const kind = value >= 0 ? "pos" : coveredMinor && -value <= coveredMinor ? "covered" : "neg";
          return (
            <motion.rect
              key={`b-${day.date}`}
              className={`bar bar-${kind}`}
              x={center(index) - barWidth / 2}
              width={barWidth}
              initial={{ y: zero, height: 0 }}
              animate={{ y: top, height: barHeight }}
              transition={{ ...spring, delay: 0.2 + index * 0.035 }}
            />
          );
        })}

        <line className="zero" x1={margin.left} x2={width - margin.right} y1={zero} y2={zero} />

        {days.map((day, index) => {
          if (!labelled.has(index)) return null;
          const value = day.balance_minor;
          const covered = value < 0 && coveredMinor >= -value;
          return (
            <motion.text
              key={`v-${day.date}`}
              className={`value ${value < 0 ? (covered ? "covered" : "neg") : ""}`}
              x={center(index)}
              y={value < 0 ? y(value) + 18 : y(value) - 9}
              textAnchor="middle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.7 + index * 0.035 }}
            >
              {moneyShort(value)}
            </motion.text>
          );
        })}

        {scenarioPath && (
          <g className="scenario">
            <motion.path
              key={`${scenario?.move.id}-${scenario?.move.date}`}
              className="scn-line"
              d={scenarioPath}
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1, ease: [0.4, 0, 0.2, 1] }}
            />
            {scenarioDays?.map((day, index) =>
              day.balance_minor !== days[index].balance_minor ? (
                <motion.circle
                  key={`s-${day.date}`}
                  className="scn-dot"
                  cx={center(index)}
                  cy={y(day.balance_minor)}
                  r={4}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ ...spring, delay: 0.5 + index * 0.04 }}
                />
              ) : null,
            )}
            {firstChange >= 0 && scenarioDays && (
              <text
                className="scn-label"
                x={center(firstChange) - 8}
                y={y(scenarioDays[firstChange].balance_minor) - 10}
                textAnchor="end"
              >
                What-if
              </text>
            )}
          </g>
        )}

        {days.map((day, index) => {
          const group = events.get(day.date);
          if (!group) return null;
          const net = group.reduce((sum, t) => sum + t.amount_minor, 0);
          const ghost = Boolean(scenario && group.every((t) => t.id === scenario.move.id));
          const label = truncate(group.length === 1 ? group[0].label : `${group.length} payments`, labelRoom(index));
          return (
            <g key={`e-${day.date}`} className={`event ${net < 0 ? "out" : "in"}${ghost ? " ghost" : ""}`}>
              <line className="event-stem" x1={center(index)} x2={center(index)} y1={eventY + 6} y2={Math.min(y(day.balance_minor), zero) - 4} />
              <circle className="event-dot" cx={center(index)} cy={eventY} r={4.5} />
              <text className="event-amount" x={center(index)} y={amountY(index, moneyShort(net, true))} textAnchor="middle">
                {moneyShort(net, true)}
              </text>
              {!narrow && label && (
                <text className="event-label" x={center(index)} y={eventY - 28} textAnchor="middle">
                  {label}
                </text>
              )}
            </g>
          );
        })}

        {movedIndex >= 0 && movedTransaction && (
          <motion.g className="event moved" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
            <line className="event-stem" x1={center(movedIndex)} x2={center(movedIndex)} y1={eventY + 6} y2={margin.top - 2} />
            <circle className="event-dot" cx={center(movedIndex)} cy={eventY} r={4.5} />
            <text
              className="event-amount"
              x={center(movedIndex)}
              y={amountY(movedIndex, moneyShort(movedTransaction.amount_minor, true))}
              textAnchor="middle"
            >
              {moneyShort(movedTransaction.amount_minor, true)}
            </text>
            {!narrow && (
              <text className="event-label" x={center(movedIndex)} y={eventY - 28} textAnchor="middle">
                moved here
              </text>
            )}
          </motion.g>
        )}

        {days.map((day, index) => (
          <g key={`x-${day.date}`} className={index === facts.firstIndex ? "x alert" : "x"}>
            <text className="x-weekday" x={center(index)} y={height - margin.bottom + 21} textAnchor="middle">
              {narrow ? weekday(day.date).slice(0, 1) : weekday(day.date).toUpperCase()}
            </text>
            <text className="x-day" x={center(index)} y={height - margin.bottom + 39} textAnchor="middle">
              {dayOfMonth(day.date)}
            </text>
          </g>
        ))}

        {days.map((day, index) => (
          <rect
            key={`h-${day.date}`}
            className="hit"
            x={left(index)}
            y={0}
            width={column}
            height={height}
            onPointerEnter={() => setHover(index)}
            onClick={() => setHover(index)}
          />
        ))}
      </svg>

      <AnimatePresence>
        {hovered && hover !== null && (
          <motion.div
            key="tip"
            className="tooltip"
            style={{
              left: Math.min(Math.max(center(hover), 124), width - 124),
              top: Math.max(margin.top + 6, Math.min(y(hovered.balance_minor), zero)),
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
          >
            <strong>{longDate(hovered.date)}</strong>
            <span className={`row ${hovered.balance_minor < 0 ? "neg" : ""}`}>
              <span>End of day</span>
              <span>{money(hovered.balance_minor)}</span>
            </span>
            {scenarioDays && (
              <span className="row scn">
                <span>What-if</span>
                <span>{money(scenarioDays[hover].balance_minor)}</span>
              </span>
            )}
            {coveredMinor > 0 && hovered.balance_minor < 0 && (
              <span className="row ok">
                <span>Covered</span>
                <span>{money(Math.min(coveredMinor, -hovered.balance_minor))}</span>
              </span>
            )}
            {(events.get(hovered.date) ?? []).map((t) => (
              <span key={t.id} className="row tx">
                <span>{t.label}</span>
                <span>{money(t.amount_minor, true)}</span>
              </span>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Hatch({ id, tone }: { id: string; tone: "red" | "green" }) {
  return (
    <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="6" height="6" className={`hatch-bg ${tone}`} />
      <line x1="0" y1="0" x2="0" y2="6" className={`hatch-line ${tone}`} />
    </pattern>
  );
}
