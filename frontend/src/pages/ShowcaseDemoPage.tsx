import { SectionHeader } from "../components/ui/Cards";
import { useTitle } from "../lib/useTitle";

const VIDEO = "/showcase/media/healwright-demo.mp4";
const POSTER = "/showcase/media/healwright-demo-poster.jpg";
const REPO = "https://github.com/zaidbinnaveed/HealWright";

const MOMENTS: { title: string; text: string }[] = [
  {
    title: "A harmless change",
    text: "The Add to cart button gets a new id. It looks the same to a shopper, but the test's selector no longer matches.",
  },
  {
    title: "A verified heal",
    text: "HealWright finds the button, replays the click in a sandbox, sees the same POST /api/cart, and the test passes.",
  },
  {
    title: "The evidence",
    text: "Screenshots, candidate scores, recorded versus observed behaviour, and a patch ready for review.",
  },
  {
    title: "A look-alike trap",
    text: "Confirm is renamed and Cancel takes its place. Cancel would send DELETE, so HealWright never picks it.",
  },
];

/** Hosted showcase: the live demo needs a local browser and test shop, so a recorded session plays instead. */
export function ShowcaseDemoPage() {
  useTitle("Live demo", "Watch HealWright heal a real Playwright test, and refuse a trap.");
  return (
    <div className="space-y-6">
      <SectionHeader as="h1" eyebrow="Live demo" title="Break it," italic="watch it heal">
        A recorded session of the real demo: the test shop is broken on purpose, the real Playwright test runs, and
        HealWright heals it, or refuses a trap. Nothing in it is staged.
      </SectionHeader>

      <section className="overflow-hidden rounded-2xl border border-line bg-black shadow-sm">
        <video
          className="block aspect-video w-full"
          src={VIDEO}
          poster={POSTER}
          controls
          playsInline
          preload="metadata"
          aria-label="Recorded HealWright demo with captions"
        >
          Your browser cannot play this video.
        </video>
      </section>

      <section aria-labelledby="moments" className="space-y-3">
        <h2 id="moments" className="text-sm font-semibold">What you will see</h2>
        <ol className="grid gap-3 sm:grid-cols-2">
          {MOMENTS.map((m, i) => (
            <li key={m.title} className="rounded-xl border border-line bg-surface p-4">
              <p className="text-xs font-medium text-dim">{String(i + 1).padStart(2, "0")}</p>
              <p className="mt-1 text-sm font-semibold">{m.title}</p>
              <p className="mt-1 text-sm text-muted">{m.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <p className="text-sm text-muted">
        Run the demo on your own machine with <code className="font-mono text-xs">healwright serve</code>: pick a
        scenario, break the page, and watch every step.{" "}
        <a href={REPO} className="font-medium text-accent-ink underline-offset-4 hover:underline">
          Get HealWright on GitHub
        </a>
        .
      </p>
    </div>
  );
}
