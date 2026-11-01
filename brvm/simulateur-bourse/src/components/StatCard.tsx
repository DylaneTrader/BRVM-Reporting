"use client";

import { motion } from "framer-motion";

export function StatCard({
  label,
  value,
  sub,
  subClass = "text-slate-400",
  accent = false,
}: {
  label: string;
  value: string;
  sub?: string;
  subClass?: string;
  accent?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`card ${accent ? "ring-1 ring-brand-500/30" : ""}`}
    >
      <div className="label">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className={`mt-1 text-sm ${subClass}`}>{sub}</div>}
    </motion.div>
  );
}
