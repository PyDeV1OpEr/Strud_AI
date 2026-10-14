/**
 * Turns the one malformed break form produced by some models into HTML that
 * the sanitized Markdown pipeline can understand. Raw `<br>` is deliberately
 * left alone: rehype-raw parses it and rehype-sanitize permits only safe HTML.
 *
 * Code samples are excluded so `\\<br>` remains a literal example there.
 */
export function normalizeEscapedBreakTags(markdown: string): string {
  let fencedBy: { character: string; length: number } | null = null;

  return markdown
    .split(/(\r?\n)/)
    .map((line) => {
      if (line === "\n" || line === "\r\n") return line;

      const fence = line.match(/^\s*(`{3,}|~{3,})/);
      if (fence) {
        const marker = fence[1];
        if (!fencedBy) {
          fencedBy = { character: marker[0], length: marker.length };
        } else if (
          marker[0] === fencedBy.character &&
          marker.length >= fencedBy.length
        ) {
          fencedBy = null;
        }
        return line;
      }
      if (fencedBy) return line;

      let normalized = "";
      let cursor = 0;
      while (cursor < line.length) {
        if (line[cursor] === "`") {
          const delimiterLength = line.slice(cursor).match(/^`+/)?.[0].length ?? 1;
          const delimiter = "`".repeat(delimiterLength);
          const closing = line.indexOf(delimiter, cursor + delimiterLength);
          if (closing === -1) return normalized + line.slice(cursor);
          normalized += line.slice(cursor, closing + delimiterLength);
          cursor = closing + delimiterLength;
          continue;
        }

        const breakTag = line.slice(cursor).match(/^\\(<br\s*\/?\s*>)/i);
        if (breakTag) {
          normalized += breakTag[1];
          cursor += breakTag[0].length;
          continue;
        }

        normalized += line[cursor];
        cursor += 1;
      }
      return normalized;
    })
    .join("");
}
