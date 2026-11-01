"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Tableau de bord" },
  { href: "/market", label: "Marché" },
  { href: "/strategie", label: "Stratégie" },
  { href: "/portfolio", label: "Portefeuille" },
  { href: "/transactions", label: "Transactions" },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b border-white/5 bg-base-900/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 font-bold text-white">
            B
          </span>
          <span className="font-semibold tracking-tight">
            Simulateur <span className="text-brand-500">BRVM</span>
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          {links.map((l) => {
            const active =
              l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  active
                    ? "bg-white/10 text-white"
                    : "text-slate-400 hover:text-slate-100 hover:bg-white/5"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
