import type { Metadata } from "next";
import recordedData from "./recorded-data.json";
import Showcase from "./viewer";

export const metadata: Metadata = {
  title: "Evidence Viewer | Agent Reliability Lab",
  description:
    "Inspect a recorded AI investigation, compare reliability results, and replay an operator-approved worker restart.",
};

export default function ShowcasePage() {
  return <Showcase {...recordedData} />;
}
