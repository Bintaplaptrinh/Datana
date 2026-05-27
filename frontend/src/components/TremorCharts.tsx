"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import styles from "./TremorCharts.module.css";

export interface ChartDatum {
  label: string;
  count: number;
}

const numberFormatter = new Intl.NumberFormat("en-US");

export function TremorBarChart({ data }: { data: ChartDatum[] }) {
  return (
    <div className={styles.chart} tremor-id="tremor-raw">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={data} margin={{ top: 10, right: 10, left: -12, bottom: 36 }}>
          <CartesianGrid vertical={false} stroke="rgba(99, 111, 130, .15)" />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            angle={-28}
            textAnchor="end"
            interval={0}
            height={62}
            tick={{ fill: "#657080", fontSize: 11 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
            tick={{ fill: "#657080", fontSize: 11 }}
          />
          <Tooltip
            cursor={{ fill: "rgba(53, 93, 245, .08)" }}
            formatter={(value) => [numberFormatter.format(Number(value)), "Records"]}
            contentStyle={{
              border: "1px solid rgba(255, 255, 255, .8)",
              borderRadius: 14,
              boxShadow: "0 12px 28px rgba(55, 68, 88, .14)",
            }}
          />
          <Bar dataKey="count" fill="#355df5" radius={[7, 7, 3, 3]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TremorDonutChart({ complete, missing }: { complete: number; missing: number }) {
  const data = [
    { label: "Complete", count: complete, color: "#355df5" },
    { label: "Missing", count: missing, color: "#cad3e2" },
  ];
  return (
    <div tremor-id="tremor-raw">
      <div className={styles.donut}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart>
            <Pie
              data={data}
              dataKey="count"
              nameKey="label"
              innerRadius={56}
              outerRadius={78}
              paddingAngle={2}
            >
              {data.map((entry) => (
                <Cell key={entry.label} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => [numberFormatter.format(Number(value)), "Values"]}
              contentStyle={{
                border: "1px solid rgba(255, 255, 255, .8)",
                borderRadius: 14,
                boxShadow: "0 12px 28px rgba(55, 68, 88, .14)",
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className={styles.legend}>
        <span><i className={styles.complete} />Complete</span>
        <span><i className={styles.missing} />Missing</span>
      </div>
    </div>
  );
}
