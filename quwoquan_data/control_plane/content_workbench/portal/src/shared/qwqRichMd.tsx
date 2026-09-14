import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { canonicalExternalUrl } from './markdown.js';

function normalizeQwqRichMd(value: string): string {
  return value
    .replace(/^:::(callout)\s+type="([^"]+)"\s+title="([^"]+)"\s*$/gm, '> **$3 ($2)**')
    .replace(/^:::(figure)\s+id="([^"]+)"[^\n]*caption="([^"]*)"\s*\nasset:\/\/[^\n]+\n:::$/gm, '![${3}](#figure-$2)')
    .replace(/^:::(gallery)[^\n]*caption="([^"]*)"\s*\n:::$/gm, '> 图集：$2')
    .replace(/^:::(align)[^\n]*\n([\s\S]*?)\n:::$/gm, '$2')
    .replace(/^:::\s*$/gm, '');
}
export function QwqRichMd({ content, source = false }: { content: string; source?: boolean }) {
  return <article className={source ? 'markdown source-gfm' : 'markdown qwq-rich-md'}><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{ a: ({ href, children }) => { const safe = canonicalExternalUrl(href); return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>; }, img: ({ alt }) => <span className="rich-media-placeholder">媒体节点：{alt || '未命名'}</span> }}>{source ? content : normalizeQwqRichMd(content)}</ReactMarkdown></article>;
}
