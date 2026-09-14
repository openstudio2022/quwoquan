export function canonicalExternalUrl(value?: string): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : undefined;
  } catch { return undefined; }
}

export function isRenderableMarkdown(mediaType?: string, kind?: string): boolean {
  return mediaType === 'text/markdown' || mediaType === 'text/x-markdown' || kind === 'markdown';
}
