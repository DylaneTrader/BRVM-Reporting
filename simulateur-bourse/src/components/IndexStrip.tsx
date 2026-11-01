"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { formatPct, pnlClass } from "@/lib/format";
import type { IndexInfo } from "@/types";

/** Bandeau des indices BRVM (valeur + variation jour). */
export function IndexStrip() {
  const [indices, setIndices] = useState<IndexInfo[]>([]);

  useEffect(() => {
    fetch("/api/indices")
      .then((r) => r.json())
      .then((d) => setIndices(d.indices || []));
  }, []);

  if (indices.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {indices.slice(0, 8).map((idx, i) => (
        <motion.div
          key={idx.symbol}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i * 0.03, 0.2) }}
          className="card p-4"
        >
          <div className="label truncate">{idx.name}</div>
          <div className="mt-1 text-xl font-semibold tracking-tight">
            {idx.value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}
          </div>
          <div className={`text-sm ${pnlClass(idx.changePct)}`}>
            {formatPct(idx.changePct)}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
