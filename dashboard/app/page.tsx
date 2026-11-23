import LegacyViewer from "./legacy-viewer";
import ShowcasePage, { metadata as showcaseMetadata } from "./showcase/page";

export const metadata =
  process.env.LAB_STATIC_EXPORT === "1" ? showcaseMetadata : {};

export default function Home() {
  return process.env.LAB_STATIC_EXPORT === "1" ? (
    <ShowcasePage />
  ) : (
    <LegacyViewer />
  );
}
