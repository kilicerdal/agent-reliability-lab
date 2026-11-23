import type { Metadata } from "next";
import "./style.css";
export const metadata: Metadata = {
  title: "Agent Reliability Lab — Evidence before confidence",
  description:
    "Inspect real local incident investigations, tool traces and independent deterministic verdicts.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
