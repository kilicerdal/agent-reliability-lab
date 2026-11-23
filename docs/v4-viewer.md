# V4 recorded evidence viewer

The static viewer opens on V1’s captured worker failure. Visitors can switch among four recorded investigations, expand tool events, and inspect the evidence behind the independent verdict. V2 compares the two prompts by incident and opens on the recorded invoice-window failure. The selector exposes every failed trial, with its expected and returned cause, citations, and raw trace. Each failure has a shareable URL that restores its selection on reload; unrecognized trial IDs open the default failure. The build checks that the incident counts reconcile with the recorded scorecard. V3 replays the worker state across request, rejection, approval, and completion. The replay controls only select captured snapshots.

## Build and preview

From the repository root, with the dashboard dependencies installed:

```sh
npm --prefix dashboard ci
npm --prefix dashboard run build:public
python3 -m http.server 3314 --bind 127.0.0.1 --directory dashboard/out
```

Open [the static preview](http://127.0.0.1:3314). To host the viewer, serve `dashboard/out` at the root of a static site. The export contains the viewer and downloadable recordings. It needs no API key, application server, database, or write endpoint. It includes the four V1 captures, V2 scorecard and 48 holdout traces, and V3 approval evidence and all six live-model traces.

The standard Next.js build retains the original V1 viewer at `/` and serves the V4 showcase at `/showcase`. The public export opens the showcase at `/`.

## Public deployment

The repository publishes the viewer through the manually dispatched `Publish recorded viewer` GitHub Actions workflow on `main`. The workflow sets the Pages project subpath and uploads only the static export. [Open the public viewer](https://kilicerdal.github.io/agent-reliability-lab/).

## Verify

```sh
npm --prefix dashboard run build:public
npm --prefix dashboard run test:public
```

The public browser suite starts a static file server and checks desktop and mobile layouts, all three evidence sections, five evidence downloads, keyboard navigation, and accessibility. It checks that browsing sends only same-origin static GET requests. V1–V3 retain their offline evidence verifiers.

- [V1 independent evaluation](evaluation.md)
- [V2 protocol and results](v2-evaluation.md)
- [V3 approval and model trials](v3-controls.md)
