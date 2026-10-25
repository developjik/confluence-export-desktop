#!/usr/bin/env node
// Builds the GitHub Pages site into _site/ from the repository's markdown docs.
// Runs in CI (`.github/workflows/pages.yml`); requires the `marked` devDependency.

import { mkdir, readFile, writeFile, cp } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "_site");

const DOCS = [
  { file: "README.md", slug: "index", title: "소개", nav: true, landing: true },
  { file: "docs/V2_PLAN.md", slug: "v2-plan", title: "V2 계획 · 골", nav: true },
  { file: "docs/PRD_v1.0.md", slug: "prd-v1", title: "v1 제품 요구사항", nav: true },
  { file: "docs/CME_FEATURE_SUPPORT.md", slug: "cme-support", title: "v1 CME 옵션 매핑", nav: true },
  { file: "docs/features/cron_background_runtime.md", slug: "v1-cron", title: "v1 백그라운드 예약", nav: true },
];

const REPO_URL = "https://github.com/developjik/confluence-export-desktop";

marked.use({ gfm: true });

const CSS = `
:root {
  --bg: #f6f7fb; --surface: #ffffff; --border: #e4e7f0; --text: #191d27;
  --muted: #5b6474; --faint: #8a93a6; --accent: #5546f0; --accent-soft: #efedfe;
  --ok: #12805c; --code-bg: #14161f;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font-family: "Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont,
    "Apple SD Gothic Neo", "Segoe UI", "Noto Sans KR", "Malgun Gothic", sans-serif;
  line-height: 1.65; font-size: 15.5px;
}
.layout { display: flex; min-height: 100vh; }
aside {
  width: 250px; shrink: 0; padding: 28px 18px; background: var(--surface);
  border-right: 1px solid var(--border); position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
.brand { display: flex; gap: 10px; align-items: center; padding: 0 10px 18px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
.brand-mark {
  width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(160deg, #6366f1, #4338ca);
  color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 15px;
}
.brand-name { font-weight: 800; font-size: 14.5px; letter-spacing: -0.01em; }
.brand-sub { font-size: 11px; color: var(--faint); }
nav a {
  display: block; padding: 8px 12px; border-radius: 9px; color: var(--muted);
  text-decoration: none; font-size: 13.5px; font-weight: 500; margin: 1px 0;
}
nav a:hover { background: var(--bg); color: var(--text); }
nav a.active { background: var(--accent-soft); color: var(--accent); }
.meta { margin-top: 22px; padding: 0 10px; font-size: 11.5px; color: var(--faint); }
.meta a { color: var(--accent); text-decoration: none; }
main { flex: 1; min-width: 0; padding: 44px 52px 90px; max-width: 980px; }
h1 { font-size: 30px; letter-spacing: -0.02em; line-height: 1.25; margin: 0 0 10px; }
h2 { font-size: 21px; letter-spacing: -0.01em; margin-top: 44px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
h3 { font-size: 16.5px; margin-top: 30px; }
p { margin: 12px 0; } 
a { color: var(--accent); }
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 13.5px; display: block; overflow-x: auto; }
th, td { border: 1px solid var(--border); padding: 8px 11px; text-align: left; vertical-align: top; }
th { background: var(--accent-soft); font-weight: 700; }
tr:nth-child(even) td { background: #fafbff; }
code { font-family: ui-monospace, SFMono-Regular, JetBrains Mono, Menlo, Consolas, monospace; font-size: 0.86em; background: var(--accent-soft); color: #3f34c9; padding: 2px 6px; border-radius: 6px; }
pre { background: var(--code-bg); color: #e6e9f2; padding: 18px 20px; border-radius: 14px; overflow-x: auto; line-height: 1.6; }
pre code { background: none; color: inherit; padding: 0; font-size: 13px; }
blockquote { margin: 14px 0; padding: 10px 16px; border-left: 3px solid var(--accent); background: var(--accent-soft); border-radius: 0 10px 10px 0; color: #3f3a6b; }
hr { border: none; border-top: 1px solid var(--border); margin: 34px 0; }
ul, ol { padding-left: 24px; }
li { margin: 4px 0; }
.badge { display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft); color: var(--accent); border: 1px solid #d8d3fb; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; margin-bottom: 18px; }
.hero { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 34px 36px; margin-bottom: 14px; box-shadow: 0 1px 2px rgb(20 22 40 / 0.05), 0 10px 30px rgb(20 22 40 / 0.05); }
.hero p { color: var(--muted); font-size: 16px; margin-top: 4px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 22px 0; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; }
.card h3 { margin: 0 0 6px; font-size: 14.5px; }
.card p { margin: 0; color: var(--muted); font-size: 13px; }
.updated { color: var(--faint); font-size: 12.5px; margin-top: 60px; }
@media (max-width: 860px) {
  aside { display: none; }
  main { padding: 28px 20px 70px; }
}
`;

const NAV_HTML = (activeSlug) => `
<nav>
  ${DOCS.filter((d) => d.nav)
    .map(
      (d) =>
        `<a href="${d.slug === "index" ? "index.html" : `${d.slug}.html`}" ${d.slug === activeSlug ? 'class="active"' : ""}>${d.title}</a>`,
    )
    .join("\n  ")}
</nav>`;

function layout({ slug, title, body, extraHead = "" }) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${title} · Confluence Export Desktop</title>
<style>${CSS}</style>
${extraHead}
</head>
<body>
<div class="layout">
  <aside>
    <div class="brand">
      <div class="brand-mark">C↓</div>
      <div>
        <div class="brand-name">Confluence Export</div>
        <div class="brand-sub">Desktop v2 · Rust + Tauri</div>
      </div>
    </div>
    ${NAV_HTML(slug)}
    <div class="meta">
      <a href="${REPO_URL}" target="_blank" rel="noopener">GitHub 저장소</a><br/>
      자동 생성 페이지 · main 브랜치 push 시 갱신
    </div>
  </aside>
  <main>${body}</main>
</div>
</body>
</html>`;
}

const SLUG_BY_PATH = new Map(DOCS.map((d) => [d.file, d.slug]));

function rewriteLinks(html) {
  return html.replace(/href="([^"]+)"/g, (match, href) => {
    const clean = href.split("#")[0];
    if (!clean.endsWith(".md")) return match;
    const anchor = href.includes("#") ? href.slice(href.indexOf("#")) : "";
    const normalized = clean.replace(/^\.\//, "");
    if (SLUG_BY_PATH.has(normalized)) {
      const slug = SLUG_BY_PATH.get(normalized);
      return `href="${slug === "index" ? "index.html" : `${slug}.html`}${anchor}"`;
    }
    return `href="${REPO_URL}/blob/main/${normalized}"`;
  });
}

async function build() {
  await mkdir(outDir, { recursive: true });
  let commitSha = process.env.GITHUB_SHA ?? "";
  let commitDate = new Date().toISOString().slice(0, 10);

  for (const doc of DOCS) {
    const file = path.join(root, doc.file);
    if (!existsSync(file)) {
      console.warn(`skip missing doc: ${doc.file}`);
      continue;
    }
    const raw = await readFile(file, "utf8");
    const html = rewriteLinks(marked.parse(raw));
    if (doc.landing) {
      const body = `
<div class="badge">v2 · Rust + Tauri · Atlassian API 직접 연동</div>
<div class="hero">
  <h1>Confluence Export Desktop</h1>
  <p>Confluence 페이지·스페이스·사이트 전체를 Markdown과 첨부파일로 내보내는 데스크톱 앱.
  Python이나 confluence-markdown-exporter 없이 자체 Rust 엔진이 크롤·변환·스킵·정리를 수행합니다.</p>
</div>
<div class="cards">
  <div class="card"><h3>Rust 엔진</h3><p>REST 클라이언트 · storage→Markdown 변환기 · lockfile 기반 skip/cleanup</p></div>
  <div class="card"><h3>새로운 UI</h3><p>대시보드 · 연결 · 작업 · 편집자 · 실행 기록 · 라이브 실행 뷰(취소 지원)</p></div>
  <div class="card"><h3>예약 실행</h3><p>매일/매주/매월 프리셋, 타임존 지원, 트레이 상주</p></div>
  <div class="card"><h3>안전한 인증</h3><p>OS 키체인 저장(Windows 자격 증명 관리자 / macOS 키체인) · v1 이관 지원</p></div>
</div>
${html}
<div class="updated">이 페이지는 main 브랜치 push 시 자동 생성됩니다.${commitSha ? ` (build ${commitSha.slice(0, 7)}, ${commitDate})` : ""}</div>`;
      await writeFile(path.join(outDir, `${doc.slug}.html`), layout({ slug: doc.slug, title: "소개", body }));
    } else {
      const body = `${html}
<div class="updated">${commitSha ? `build ${commitSha.slice(0, 7)} · ${commitDate}` : ""}</div>`;
      await writeFile(path.join(outDir, `${doc.slug}.html`), layout({ slug: doc.slug, title: doc.title, body }));
    }
    console.log(`built ${doc.slug}.html from ${doc.file}`);
  }
  console.log(`site written to ${outDir}`);
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
