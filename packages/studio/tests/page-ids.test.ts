// main.ts reads elements by id at load time. A missing id throws before the
// first fetch, and the page then shows static text with red dots. This keeps
// the script and the page in step.
import { expect, test } from "bun:test";
import { join } from "node:path";

const root = join(import.meta.dir, "..");
const script = await Bun.file(join(root, "src/main.ts")).text();
const page = await Bun.file(join(root, "index.html")).text();

function idsIn(text: string, pattern: RegExp): Set<string> {
  return new Set([...text.matchAll(pattern)].map((match) => match[1]!));
}

test("every element id the dashboard script uses exists in index.html", () => {
  const used = idsIn(script, /\$(?:<[^>]+>)?\("([a-z0-9-]+)"\)/g);
  const present = idsIn(page, /\bid="([a-z0-9-]+)"/g);
  const missing = [...used].filter((id) => !present.has(id)).sort();
  expect(missing).toEqual([]);
});

test("every page in ORDER has a section and a nav button", () => {
  const order = script.match(/const ORDER = \[([^\]]+)\]/)?.[1] ?? "";
  const pages = [...order.matchAll(/"([a-z]+)"/g)].map((match) => match[1]!);
  expect(pages.length).toBeGreaterThan(0);
  for (const name of pages) {
    expect(page).toContain(`id="page-${name}"`);
    expect(page).toContain(`data-go="${name}"`);
  }
});
