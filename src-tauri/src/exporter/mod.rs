//! Export orchestration: crawl → plan paths → convert → attachments →
//! skip/cleanup via lockfile → progress reporting.

pub mod lockfile;
pub mod paths;

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use futures::StreamExt;
use once_cell::sync::Lazy;
use serde::Serialize;
use sha2::{Digest, Sha256};
use tokio::sync::mpsc::UnboundedSender;

use crate::confluence::client::{ClientConfig, ConfluenceClient};
use crate::confluence::types::{ApiAttachment, ApiPage};
use crate::confluence::urls::{self, Target};
use crate::converter::{self, ConvertOptions, ExportIndex, IndexedAttachment, IndexedPage, PageMeta};
use crate::error::{AppError, AppResult, CancelFlag};
use crate::models::{Job, RunStats, Scope};

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum ProgressEvent {
    Phase { phase: String },
    Message { text: String },
    Total { total: usize },
    PageStart { id: String, title: String },
    PageDone { id: String, title: String, outcome: String, path: Option<String> },
    Stats { stats: RunStats },
}

#[derive(Debug, Clone)]
pub struct ExportOutcome {
    pub scope: Scope,
    pub urls: Vec<String>,
    pub stats: RunStats,
    pub cancelled: bool,
}

static RI_PAGE_TAG: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r#"<ri:page\b[^>]*>"#).unwrap());
static RI_ATTACHMENT_TITLE: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r#"<ri:attachment\b[^>]*>"#).unwrap());
static ATTR_VALUE: Lazy<regex::Regex> =
    Lazy::new(|| regex::Regex::new(r#"\b(ri:content-title|ri:space-key|ri:filename)="([^"]*)""#).unwrap());

pub async fn run_export(
    job: &Job,
    base_url: &str,
    email: &str,
    token: &str,
    progress: &UnboundedSender<ProgressEvent>,
    cancel: &CancelFlag,
) -> AppResult<ExportOutcome> {
    let opts = &job.export_options;
    let target_dir = PathBuf::from(&job.target_dir);
    if job.target_dir.trim().is_empty() {
        return Err(AppError::config("TARGET_DIR_REQUIRED", "대상 폴더를 지정하세요.", ""));
    }
    std::fs::create_dir_all(&target_dir).map_err(|err| {
        AppError::config("TARGET_DIR_UNAVAILABLE", "대상 폴더를 만들거나 열 수 없습니다.", format!("{}: {err}", target_dir.display()))
    })?;

    let client = ConfluenceClient::new(
        base_url,
        email,
        token,
        ClientConfig { timeout_seconds: opts.timeout_seconds, max_retries: 5 },
    )?;
    let scope = job.resolve_scope()?;
    let urls = job.export_urls()?;
    let convert_options = ConvertOptions::from_export_options(opts);

    // ---------- discovery ----------
    send(progress, ProgressEvent::Phase { phase: "discover".into() });
    let mut pages: Vec<ApiPage> = Vec::new();
    let mut seen_ids: HashSet<String> = HashSet::new();
    for url in &urls {
        check_cancelled(cancel)?;
        send(progress, ProgressEvent::Message { text: format!("수집 중: {url}") });
        let target = urls::parse_target(base_url, url)?;
        let found: AppResult<Vec<ApiPage>> = match &target {
            Target::Page { id, .. } => client.get_page(id).await.map(|p| vec![p]),
            Target::Space { key } => client.space_pages(key).await,
            Target::Org => {
                let mut all = Vec::new();
                for space in client.list_spaces().await? {
                    check_cancelled(cancel)?;
                    send(progress, ProgressEvent::Message { text: format!("스페이스 수집: {}", space.key) });
                    all.extend(client.space_pages(&space.key).await?);
                }
                Ok(all)
            }
        };
        let found = match found {
            Ok(found) => found,
            Err(err) => return Err(err),
        };
        for page in found {
            if seen_ids.insert(page.id.clone()) {
                pages.push(page);
            }
        }
    }
    if scope == Scope::PagesWithDescendants {
        // expand each root page into its full subtree
        let mut expanded: Vec<ApiPage> = Vec::new();
        let mut expanded_ids: HashSet<String> = HashSet::new();
        for url in &urls {
            check_cancelled(cancel)?;
            if let Target::Page { id, .. } = urls::parse_target(base_url, url)? {
                let subtree = client
                    .collect_with_descendants(&id, opts.max_requests, cancel)
                    .await?;
                for page in subtree {
                    if expanded_ids.insert(page.id.clone()) {
                        expanded.push(page);
                    }
                }
            }
        }
        for page in expanded {
            if seen_ids.insert(page.id.clone()) {
                pages.push(page);
            }
        }
    }
    if pages.is_empty() {
        return Err(AppError::config("NOTHING_TO_EXPORT", "내보낼 페이지를 찾지 못했습니다.", urls.join(", ")));
    }
    send(progress, ProgressEvent::Total { total: pages.len() });

    // ---------- space homepages ----------
    let needs_homepage = opts.page_path.contains("{homepage_title}");
    let mut homepage_ids: HashMap<String, String> = HashMap::new();
    let mut homepage_titles: HashMap<String, String> = HashMap::new();
    if needs_homepage {
        let space_keys: Vec<String> = pages
            .iter()
            .map(|p| p.space.key.clone())
            .filter(|k| !k.is_empty())
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();
        for key in space_keys {
            check_cancelled(cancel)?;
            if let Ok(space) = client.get_space(&key).await {
                if let Some(home_id) = space.homepage_id {
                    if let Ok(home) = client.get_page(&home_id).await {
                        homepage_titles.insert(key.clone(), home.title);
                    }
                    homepage_ids.insert(key, home_id);
                }
            }
        }
    }

    // ---------- attachments ----------
    send(progress, ProgressEvent::Phase { phase: "attachments".into() });
    let mut attachments_by_page: HashMap<String, Vec<ApiAttachment>> = HashMap::new();
    for page in &pages {
        check_cancelled(cancel)?;
        match client.page_attachments(&page.id).await {
            Ok(list) => attachments_by_page.insert(page.id.clone(), list),
            Err(err) => {
                tracing::warn!("attachment listing failed for page {}: {err}", page.id);
                attachments_by_page.insert(page.id.clone(), Vec::new())
            }
        };
    }
    if !opts.attachment_export_all {
        let referenced = collect_referenced_attachments(&pages);
        for list in attachments_by_page.values_mut() {
            list.retain(|att| referenced.contains(&att.title.to_lowercase()));
        }
    }

    // ---------- path planning ----------
    let mut allocator = paths::PathAllocator::new();
    let mut page_rel_paths: HashMap<String, String> = HashMap::new();
    for page in &pages {
        let ctx = paths::PagePathCtx {
            space_key: &page.space.key,
            space_name: page.space.name.as_deref().unwrap_or(&page.space.key),
            homepage_title: homepage_titles.get(&page.space.key).map(String::as_str),
            ancestors: ancestors_below_homepage(page, homepage_ids.get(&page.space.key))
                .into_iter()
                .map(|a| a.title.as_str())
                .collect(),
            page_title: &page.title,
        };
        let rendered = paths::render_page_path(&opts.page_path, &ctx, opts.filename_max_length);
        page_rel_paths.insert(page.id.clone(), allocator.allocate(&rendered));
    }
    let attachment_key = |att: &ApiAttachment| -> String {
        att.file_id
            .clone()
            .filter(|id| !id.is_empty())
            .unwrap_or_else(|| format!("att-{}", att.id))
    };
    let mut attachment_rel_paths: HashMap<(String, String), String> = HashMap::new(); // (page_id, key) -> path
    for page in &pages {
        if let Some(list) = attachments_by_page.get(&page.id) {
            for att in list {
                let ctx = paths::AttachmentPathCtx {
                    space_key: &page.space.key,
                    space_name: page.space.name.as_deref().unwrap_or(&page.space.key),
                    page_title: &page.title,
                    file_id: &attachment_key(att),
                    file_name: &att.title,
                    extension: &att.extension(),
                };
                let rendered = paths::render_attachment_path(&opts.attachment_path, &ctx, opts.filename_max_length);
                attachment_rel_paths.insert((page.id.clone(), attachment_key(att)), allocator.allocate(&rendered));
            }
        }
    }

    // ---------- link index ----------
    let mut index = ExportIndex {
        base_url: client.base_url().to_string(),
        ..Default::default()
    };
    for page in &pages {
        let rel_path = page_rel_paths[&page.id].clone();
        index.pages_by_id.insert(
            page.id.clone(),
            IndexedPage { rel_path: rel_path.clone(), web_url: page.web_url(client.base_url()) },
        );
        if !page.space.key.is_empty() {
            index
                .page_ids_by_title
                .insert((page.space.key.to_lowercase(), page.title.clone()), page.id.clone());
        }
    }
    for page in &pages {
        if let Some(list) = attachments_by_page.get(&page.id) {
            for att in list {
                let key = attachment_key(att);
                if let Some(rel_path) = attachment_rel_paths.get(&(page.id.clone(), key.clone())) {
                    index.attachments_by_file_id.insert(
                        key.clone(),
                        IndexedAttachment { rel_path: rel_path.clone(), title: att.title.clone(), page_id: page.id.clone() },
                    );
                    index
                        .attachment_ids_by_title
                        .insert(att.title.to_lowercase(), key);
                }
            }
        }
    }

    // ---------- external page link resolution ----------
    let unresolved = collect_unresolved_page_links(&pages, &index);
    let mut resolved = 0usize;
    for (space_key, title) in unresolved.iter().take(100) {
        check_cancelled(cancel)?;
        match client.search_page_by_title(space_key, title).await {
            Ok(Some((id, webui))) => {
                index
                    .external_pages
                    .insert((space_key.clone(), title.clone()), (id, webui));
                resolved += 1;
            }
            Ok(None) => {
                index
                    .external_pages
                    .insert((space_key.clone(), title.clone()), (String::new(), String::new()));
            }
            Err(err) => tracing::warn!("link resolution failed for {title}: {err}"),
        }
    }
    if resolved > 0 {
        send(progress, ProgressEvent::Message { text: format!("외부 페이지 링크 {resolved}개 확인") });
    }

    // ---------- convert & write ----------
    send(progress, ProgressEvent::Phase { phase: "convert".into() });
    let mut lock = lockfile::Lockfile::load(&target_dir);
    let mut stats = RunStats {
        pages_total: pages.len(),
        attachments_total: attachments_by_page.values().map(Vec::len).sum(),
        ..Default::default()
    };
    let mut cancelled = false;

    for page in &pages {
        if cancel.is_cancelled() {
            cancelled = true;
            break;
        }
        send(progress, ProgressEvent::PageStart { id: page.id.clone(), title: page.title.clone() });
        let rel_path = &page_rel_paths[&page.id];
        if rel_path.split('/').any(|seg| seg == "..") {
            return Err(AppError::config("PATH_ESCAPE", "출력 경로가 대상 폴더를 벗어납니다.", rel_path));
        }
        let existing = lock.pages.get(&page.id);
        let file_path = target_dir.join(rel_path);
        let should_skip = opts.skip_unchanged
            && existing
                .map(|e| e.version == page.version && e.path == *rel_path && file_path.exists())
                .unwrap_or(false);

        let entry = lock
            .pages
            .entry(page.id.clone())
            .or_default();

        if should_skip {
            stats.pages_skipped += 1;
            send(progress, ProgressEvent::PageDone {
                id: page.id.clone(),
                title: page.title.clone(),
                outcome: "skipped".into(),
                path: Some(rel_path.clone()),
            });
        } else {
            let meta = PageMeta {
                id: page.id.clone(),
                title: page.title.clone(),
                space_key: page.space.key.clone(),
                space_name: page.space.name.clone().unwrap_or_else(|| page.space.key.clone()),
                web_url: page.web_url(client.base_url()),
                ancestors: page
                    .ancestors
                    .iter()
                    .map(|a| converter::AncestorLink { id: a.id.clone(), title: a.title.clone() })
                    .collect(),
                homepage_id: homepage_ids.get(&page.space.key).cloned(),
                version: page.version,
                updated: None,
                rel_path: rel_path.clone(),
            };
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                converter::convert_page(&meta, &page.storage, &index, &convert_options)
            })) {
                Ok(markdown) => {
                    if let Some(parent) = file_path.parent() {
                        std::fs::create_dir_all(parent).map_err(|err| {
                            AppError::new("Storage", "WRITE_FAILED", "파일을 저장하지 못했습니다.", format!("{}: {err}", parent.display()), false)
                        })?;
                    }
                    tokio::fs::write(&file_path, &markdown)
                        .await
                        .map_err(|err| AppError::new("Storage", "WRITE_FAILED", "파일을 저장하지 못했습니다.", format!("{}: {err}", file_path.display()), false))?;
                    let hash = hex::encode(Sha256::digest(markdown.as_bytes()));
                    entry.version = page.version;
                    entry.path = rel_path.clone();
                    entry.hash = hash;
                    stats.pages_exported += 1;
                    send(progress, ProgressEvent::PageDone {
                        id: page.id.clone(),
                        title: page.title.clone(),
                        outcome: "exported".into(),
                        path: Some(rel_path.clone()),
                    });
                }
                Err(_) => {
                    stats.pages_failed += 1;
                    tracing::error!("conversion panicked for page {} ({})", page.id, page.title);
                    send(progress, ProgressEvent::PageDone {
                        id: page.id.clone(),
                        title: page.title.clone(),
                        outcome: "failed".into(),
                        path: None,
                    });
                }
            }
        }

        // attachments of this page (version-compared even when the page was skipped)
        if let Some(list) = attachments_by_page.get(&page.id) {
            let downloads: Vec<(usize, String, String)> = list
                .iter()
                .enumerate()
                .filter(|(_, att)| {
                    let key = attachment_key(att);
                    let rel = &attachment_rel_paths[&(page.id.clone(), key.clone())];
                    let path = target_dir.join(rel);
                    let known = entry.attachments.get(&key);
                    !(known.map(|k| k.version == att.version).unwrap_or(false) && path.exists())
                })
                .map(|(idx, att)| (idx, attachment_key(att), att.download_path.clone()))
                .collect();
            if !downloads.is_empty() {
                let mut results: Vec<(usize, String, String, AppResult<Vec<u8>>)> = Vec::new();
                {
                    let mut stream = futures::stream::iter(downloads.iter().cloned())
                        .map(|(idx, key, download_path)| {
                            let client = &client;
                            async move {
                                let result = client.download_attachment(&download_path).await;
                                (idx, key, download_path, result)
                            }
                        })
                        .buffer_unordered(opts.max_requests.max(1));
                    while let Some(item) = stream.next().await {
                        if cancel.is_cancelled() {
                            break;
                        }
                        results.push(item);
                    }
                }
                for (idx, key, _, result) in results {
                    let att = &list[idx];
                    let rel = attachment_rel_paths[&(page.id.clone(), key.clone())].clone();
                    let path = target_dir.join(&rel);
                    match result {
                        Ok(bytes) => {
                            if let Some(parent) = path.parent() {
                                let _ = std::fs::create_dir_all(parent);
                            }
                            match tokio::fs::write(&path, &bytes).await {
                                Ok(()) => {
                                    entry
                                        .attachments
                                        .insert(key.clone(), lockfile::LockAttachment { version: att.version, path: rel.clone() });
                                    stats.attachments_exported += 1;
                                }
                                Err(err) => {
                                    tracing::warn!("attachment write failed {}: {err}", path.display());
                                }
                            }
                        }
                        Err(err) => {
                            tracing::warn!("attachment download failed ({}) {}: {err}", page.id, att.title);
                        }
                    }
                }
            }
            stats.attachments_skipped = stats
                .attachments_total
                .saturating_sub(stats.attachments_exported);
        }

        send(progress, ProgressEvent::Stats { stats: stats.clone() });
    }

    // ---------- stale cleanup ----------
    if opts.cleanup_stale && !cancelled && matches!(scope, Scope::Spaces | Scope::Orgs | Scope::PagesWithDescendants) {
        send(progress, ProgressEvent::Phase { phase: "cleanup".into() });
        let stale_ids: Vec<String> = lock
            .pages
            .keys()
            .filter(|id| !seen_ids.contains(*id))
            .cloned()
            .collect();
        for id in stale_ids {
            if let Some(entry) = lock.pages.remove(&id) {
                delete_file_safely(&target_dir, &entry.path, &mut stats);
                for att in entry.attachments.values() {
                    delete_file_safely(&target_dir, &att.path, &mut stats);
                }
            }
        }
        // attachment-level staleness for pages that still exist
        let current_att_keys: HashMap<String, HashSet<String>> = attachments_by_page
            .iter()
            .map(|(page_id, list)| {
                (
                    page_id.clone(),
                    list.iter().map(|a| attachment_key(a)).collect::<HashSet<_>>(),
                )
            })
            .collect();
        for (page_id, entry) in lock.pages.iter_mut() {
            let mut remove_keys: Vec<String> = Vec::new();
            if let Some(current) = current_att_keys.get(page_id) {
                for (key, att) in &entry.attachments {
                    if !current.contains(key) {
                        delete_file_safely(&target_dir, &att.path, &mut stats);
                        remove_keys.push(key.clone());
                    }
                }
            }
            for key in remove_keys {
                entry.attachments.remove(&key);
            }
        }
    }

    lock.schema_version = lockfile::Lockfile::SCHEMA_VERSION;
    lock.save(&target_dir)?;

    send(progress, ProgressEvent::Phase { phase: "done".into() });
    if cancelled {
        check_cancelled(cancel)?; // surface a proper cancellation error object
    }
    Ok(ExportOutcome { scope, urls, stats, cancelled: false })
}

fn send(progress: &UnboundedSender<ProgressEvent>, event: ProgressEvent) {
    let _ = progress.send(event);
}

fn check_cancelled(cancel: &CancelFlag) -> AppResult<()> {
    if cancel.is_cancelled() {
        Err(AppError::new("Run", "CANCELLED", "실행이 취소되었습니다.", "", false))
    } else {
        Ok(())
    }
}

fn ancestors_below_homepage<'a>(
    page: &'a ApiPage,
    homepage_id: Option<&String>,
) -> Vec<&'a crate::confluence::types::AncestorRef> {
    match homepage_id.and_then(|hid| page.ancestors.iter().position(|a| &a.id == hid)) {
        Some(idx) => page.ancestors[idx + 1..].iter().collect(),
        None => page.ancestors.iter().collect(),
    }
}

fn delete_file_safely(target_dir: &std::path::Path, rel_path: &str, stats: &mut RunStats) {
    if rel_path.is_empty() {
        return;
    }
    let path = target_dir.join(rel_path);
    match std::fs::remove_file(&path) {
        Ok(()) => {
            stats.files_removed += 1;
            tracing::info!("removed stale file {}", path.display());
        }
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
        Err(err) => tracing::warn!("failed to remove stale file {}: {err}", path.display()),
    }
}

/// Attachment titles referenced from page bodies (used when
/// `attachment_export_all` is off).
fn collect_referenced_attachments(pages: &[ApiPage]) -> HashSet<String> {
    let mut out = HashSet::new();
    for page in pages {
        for capture in RI_ATTACHMENT_TITLE.captures_iter(&page.storage) {
            let tag = capture.get(0).map(|m| m.as_str()).unwrap_or_default();
            for attr in ATTR_VALUE.captures_iter(tag) {
                if &attr[1] == "ri:filename" {
                    out.insert(unescape_xml(&attr[2]).to_lowercase());
                }
            }
        }
    }
    out
}

/// (space_key lowercase, title) page links that are not part of the export set.
fn collect_unresolved_page_links(
    pages: &[ApiPage],
    index: &ExportIndex,
) -> Vec<(String, String)> {
    let mut wanted: Vec<(String, String)> = Vec::new();
    let mut dedup: HashSet<(String, String)> = HashSet::new();
    for page in pages {
        for capture in RI_PAGE_TAG.captures_iter(&page.storage) {
            let tag = capture.get(0).map(|m| m.as_str()).unwrap_or_default();
            let mut title: Option<String> = None;
            let mut space: Option<String> = None;
            for attr in ATTR_VALUE.captures_iter(tag) {
                match &attr[1] {
                    "ri:content-title" => title = Some(unescape_xml(&attr[2])),
                    "ri:space-key" => space = Some(unescape_xml(&attr[2])),
                    _ => {}
                }
            }
            let Some(title) = title else { continue };
            if title.is_empty() {
                continue;
            }
            let space_key = space.unwrap_or_else(|| page.space.key.clone());
            let key = (space_key.to_lowercase(), title);
            if index.page_ids_by_title.contains_key(&key) || index.external_pages.contains_key(&key) {
                continue;
            }
            if dedup.insert(key.clone()) {
                wanted.push(key);
            }
        }
    }
    wanted
}

fn unescape_xml(text: &str) -> String {
    text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&#39;", "'")
        .replace("&nbsp;", "\u{00a0}")
        .replace("&amp;", "&")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn referenced_attachments_extraction() {
        let pages = vec![ApiPage {
            id: "1".into(),
            title: "P".into(),
            space: crate::confluence::types::SpaceRef { key: "K".into(), name: Some("K".into()) },
            version: 1,
            ancestors: vec![],
            storage: r#"<p><ac:image><ri:attachment ri:filename="Shot One.png"/></ac:image></p><ac:link><ri:attachment ri:filename="doc.pdf"/></ac:link>"#.into(),
            webui: "/x".into(),
        }];
        let refs = collect_referenced_attachments(&pages);
        assert!(refs.contains("shot one.png"));
        assert!(refs.contains("doc.pdf"));
        assert_eq!(refs.len(), 2);
    }

    #[test]
    fn unresolved_links_dedup() {
        let pages = vec![ApiPage {
            id: "1".into(),
            title: "P".into(),
            space: crate::confluence::types::SpaceRef { key: "K".into(), name: None },
            version: 1,
            ancestors: vec![],
            storage: r#"<ac:link><ri:page ri:content-title="Other &amp; Page" ri:space-key="K"/></ac:link><ac:link><ri:page ri:content-title="Other &amp; Page"/></ac:link>"#.into(),
            webui: "/x".into(),
        }];
        let unresolved = collect_unresolved_page_links(&pages, &ExportIndex::default());
        assert_eq!(unresolved.len(), 1);
        assert_eq!(unresolved[0], ("k".into(), "Other & Page".into()));
    }
}
