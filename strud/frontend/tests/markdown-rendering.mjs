import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { normalizeEscapedBreakTags } from "../lib/markdown.ts";

function render(markdown) {
  return renderToStaticMarkup(
    createElement(
      ReactMarkdown,
      { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeRaw, rehypeSanitize] },
      normalizeEscapedBreakTags(markdown),
    ),
  );
}

// Simple factual answer: one concise paragraph, no default table or heading.
const simple = render("Mitochondria release usable energy from food through cellular respiration.");
assert.match(simple, /^<p>Mitochondria/);
assert.doesNotMatch(simple, /<table|<h[1-6]/);

// Detailed and Biology answers retain semantic paragraphs, headings, and emphasis.
const detailed = render("## Why diffusion matters\n\n**Diffusion** moves particles down a concentration gradient. This helps cells exchange gases.");
assert.match(detailed, /<h2>Why diffusion matters<\/h2>.*<strong>Diffusion<\/strong>/s);
const biology = render("## Photosynthesis\n\nChlorophyll absorbs light energy. For example, a leaf uses that energy to make glucose from carbon dioxide and water.");
assert.match(biology, /<h2>Photosynthesis<\/h2>.*make glucose/s);

// A table is preserved for a genuine side-by-side comparison only.
assert.match(render("| Feature | Mitosis | Meiosis |\n| --- | --- | --- |\n| Products | 2 cells | 4 cells |"), /<table>.*<th>Feature<\/th>/s);

// Ordered procedures, bullets, headings, and both break forms render correctly.
const escapedBreak = "\\" + "<br>";
assert.match(render(`# Process\n\n- First point\n- Second point\n\n1. Start\n2. Finish\n\nLine one<br>Line two${escapedBreak}Line three`), /<h1>Process<\/h1>.*<ul>.*<ol>.*Line one<br\/?\s*>Line two<br\/?\s*>Line three/s);
assert.match(render("A<br>B"), /A<br\/?\s*>B/);
assert.match(render("| Term | Meaning |\n| --- | --- |\n| DNA | Stores<br>instructions |"), /Stores<br\/?\s*>instructions/);
// Literal tags are still literal in code blocks.
assert.match(render("```html\n<br>\n```"), /<code class="language-html">&lt;br&gt;\n?<\/code>/);

const escaped = `First${"\\"}<br>second\n\n\`${"\\"}<br>\`\n\n\`\`\`html\n${"\\"}<br>\n\`\`\``;
assert.equal(
  normalizeEscapedBreakTags(escaped),
  "First<br>second\n\n`\\<br>`\n\n```html\n\\<br>\n```",
);

console.log("Markdown rendering regressions passed.");
