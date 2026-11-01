import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Simulateur de portefeuille BRVM",
  description:
    "Simulateur local de portefeuille boursier BRVM — liquidités fictives, achat/vente, suivi de valeur et historique.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className="min-h-screen antialiased">
        <NavBar />
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 py-8 text-center text-xs text-slate-500">
          Simulateur éducatif — données BRVM (cours de clôture). Pas de conseil en
          investissement. Vente à découvert interdite (règle BRVM).
        </footer>
      </body>
    </html>
  );
}
