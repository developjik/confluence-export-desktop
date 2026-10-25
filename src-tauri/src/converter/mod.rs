//! Confluence storage format → Markdown converter.

pub mod emit;
pub mod preprocess;
pub mod tree;

use std::collections::HashMap;

use crate::models::HrefMode;

/// Everything the converter needs to know about the page being converted.
#[derive(Debug, Clone)]
pub struct PageMeta {
    pub id: String,
    pub title: String,
    pub space_key: String,
    pub space_name: String,
    pub web_url: String,
    /// Ancestors ordered root → parent.
    pub ancestors: Vec<AncestorLink>,
    pub homepage_id: Option<String>,
    pub version: i64,
    pub updated: Option<String>,
    /// '/'-separated path of this page's file relative to the export root.
    pub rel_path: String,
}

#[derive(Debug, Clone)]
pub struct AncestorLink {
    pub id: String,
    pub title: String,
}

impl PageMeta {
    /// Ancestors below the space homepage (homepage itself excluded) —
    /// mirrors CME's `{ancestor_titles}` semantics when `{homepage_title}` is used.
    pub fn ancestors_below_homepage(&self) -> Vec<&AncestorLink> {
        match self.homepage_id.as_deref().and_then(|hid| {
            self.ancestors.iter().position(|a| a.id == hid)
        }) {
            Some(idx) => self.ancestors[idx + 1..].iter().collect(),
            None => self.ancestors.iter().collect(),
        }
    }

}

#[derive(Debug, Clone)]
pub struct IndexedPage {
    pub rel_path: String,
    pub web_url: String,
}

#[derive(Debug, Clone)]
pub struct IndexedAttachment {
    pub rel_path: String,
    pub title: String,
    pub page_id: String,
}

/// Lookup tables shared across the export run: all exported pages/attachments
/// plus externally resolved links (pages outside the export set).
#[derive(Debug, Clone, Default)]
pub struct ExportIndex {
    pub base_url: String,
    pub pages_by_id: HashMap<String, IndexedPage>,
    /// (space_key lowercase, title) → page id.
    pub page_ids_by_title: HashMap<(String, String), String>,
    pub attachments_by_file_id: HashMap<String, IndexedAttachment>,
    /// attachment title (lowercased) → file id.
    pub attachment_ids_by_title: HashMap<String, String>,
    /// (space_key lowercase, title) → (page id, webui path) for pages outside the set.
    pub external_pages: HashMap<(String, String), (String, String)>,
}

impl ExportIndex {
    pub fn lookup_page(&self, space_key: &str, title: &str) -> Option<&IndexedPage> {
        let key = (space_key.to_lowercase(), title.to_string());
        self.page_ids_by_title
            .get(&key)
            .and_then(|id| self.pages_by_id.get(id))
    }

    pub fn lookup_attachment(&self, title: &str) -> Option<&IndexedAttachment> {
        self.attachment_ids_by_title
            .get(&title.to_lowercase())
            .and_then(|id| self.attachments_by_file_id.get(id))
    }

    pub fn external_page_url(&self, space_key: &str, title: &str) -> Option<String> {
        let key = (space_key.to_lowercase(), title.to_string());
        self.external_pages.get(&key).map(|(_, webui)| {
            format!("{}/wiki{}", self.base_url.trim_end_matches('/'), webui)
        })
    }

    pub fn attachment_web_url(&self, att: &IndexedAttachment) -> String {
        format!(
            "{}/wiki/download/attachments/{}/{}",
            self.base_url.trim_end_matches('/'),
            att.page_id,
            encode_segment(&att.title)
        )
    }
}

#[derive(Debug, Clone)]
pub struct ConvertOptions {
    pub page_link: HrefMode,
    pub attachment_link: HrefMode,
    pub include_document_title: bool,
    pub page_breadcrumbs: bool,
    pub page_properties_as_front_matter: bool,
    pub front_matter_standard: bool,
}

impl ConvertOptions {
    pub fn from_export_options(opts: &crate::models::ExportOptions) -> Self {
        Self {
            page_link: HrefMode::parse(&opts.page_link).unwrap_or_default(),
            attachment_link: HrefMode::parse(&opts.attachment_link).unwrap_or_default(),
            include_document_title: opts.include_document_title,
            page_breadcrumbs: opts.page_breadcrumbs,
            page_properties_as_front_matter: opts.page_properties_as_front_matter,
            front_matter_standard: opts.front_matter_standard,
        }
    }
}

/// Convert one page's storage format body into a full Markdown document.
pub fn convert_page(
    page: &PageMeta,
    storage: &str,
    index: &ExportIndex,
    options: &ConvertOptions,
) -> String {
    let prepared = preprocess::preprocess(storage);
    let dom = scraper::Html::parse_document(&prepared);
    let simplified = tree::simplify(&dom);
    let body_out = emit::emit_body(&simplified, page, index, options);

    let mut sections: Vec<String> = Vec::new();

    let mut front_matter = Vec::new();
    if options.front_matter_standard {
        front_matter.push(("title".to_string(), yaml_scalar(&page.title)));
        front_matter.push(("url".to_string(), yaml_scalar(&page.web_url)));
        if !page.space_key.is_empty() {
            front_matter.push(("space".to_string(), yaml_scalar(&page.space_key)));
            if !page.space_name.is_empty() {
                front_matter.push(("space_name".to_string(), yaml_scalar(&page.space_name)));
            }
        }
        front_matter.push(("page_id".to_string(), yaml_scalar(&page.id)));
        front_matter.push(("version".to_string(), page.version.to_string()));
        if let Some(updated) = &page.updated {
            front_matter.push(("updated".to_string(), yaml_scalar(updated)));
        }
    }
    if options.page_properties_as_front_matter {
        for (key, value) in &body_out.properties {
            front_matter.push((key.clone(), yaml_scalar(value)));
        }
    }
    if !front_matter.is_empty() {
        let mut block = String::from("---\n");
        for (key, value) in &front_matter {
            block.push_str(&format!("{key}: {value}\n"));
        }
        block.push_str("---");
        sections.push(block);
    }

    if options.page_breadcrumbs {
        let crumbs = breadcrumbs(page, index);
        if !crumbs.is_empty() {
            sections.push(crumbs);
        }
    }

    if options.include_document_title {
        sections.push(format!("# {}", escape_heading_text(&page.title)));
    }

    if !body_out.markdown.trim().is_empty() {
        sections.push(body_out.markdown.trim().to_string());
    }

    sections.join("\n\n") + "\n"
}

fn breadcrumbs(page: &PageMeta, index: &ExportIndex) -> String {
    let base = index.base_url.trim_end_matches('/');
    let mut parts: Vec<String> = Vec::new();
    if !page.space_name.is_empty() || !page.space_key.is_empty() {
        let label = if page.space_name.is_empty() {
            page.space_key.clone()
        } else {
            page.space_name.clone()
        };
        parts.push(format!(
            "[{}]({}/wiki/spaces/{})",
            escape_label(&label),
            base,
            encode_segment(&page.space_key)
        ));
    }
    for ancestor in page.ancestors_below_homepage() {
        let url = format!("{}/wiki/spaces/{}/pages/{}", base, encode_segment(&page.space_key), ancestor.id);
        parts.push(format!("[{}]({})", escape_label(&ancestor.title), url));
    }
    parts.push(format!("**{}**", escape_label(&page.title)));
    parts.join(" > ")
}

// ---------- href helpers ----------

/// Percent-encode one path segment for use in a Markdown link target.
pub fn encode_segment(segment: &str) -> String {
    const SET: &percent_encoding::AsciiSet = &percent_encoding::CONTROLS
        .add(b' ')
        .add(b'"')
        .add(b'#')
        .add(b'%')
        .add(b'<')
        .add(b'>')
        .add(b'?')
        .add(b'`')
        .add(b'{')
        .add(b'}')
        .add(b'(')
        .add(b')');
    percent_encoding::utf8_percent_encode(segment, SET).to_string()
}

fn encode_rel_path(rel: &str) -> String {
    rel.split('/')
        .map(encode_segment)
        .collect::<Vec<_>>()
        .join("/")
}

/// href for a target file given the converter's link mode.
pub fn file_href(mode: HrefMode, target_rel: &str, from_page_rel: &str, wiki_url: &str) -> String {
    match mode {
        HrefMode::Wiki => wiki_url.to_string(),
        HrefMode::Absolute => format!("/{}", encode_rel_path(target_rel)),
        HrefMode::Relative => relative_href(from_page_rel, target_rel),
    }
}

/// Compute a `../`-style href between two export-root-relative paths.
pub fn relative_href(from_rel: &str, to_rel: &str) -> String {
    let from_segs: Vec<&str> = from_rel.split('/').collect();
    let to_segs: Vec<&str> = to_rel.split('/').collect();
    let mut common = 0usize;
    while common + 1 < from_segs.len() && common + 1 < to_segs.len() && from_segs[common] == to_segs[common] {
        common += 1;
    }
    let ups = from_segs.len() - 1 - common;
    let mut parts: Vec<String> = Vec::new();
    for _ in 0..ups {
        parts.push("..".to_string());
    }
    for seg in &to_segs[common..] {
        parts.push(encode_segment(seg));
    }
    if parts.is_empty() {
        encode_segment(to_segs.last().copied().unwrap_or_default())
    } else {
        parts.join("/")
    }
}

// ---------- text helpers ----------

fn yaml_scalar(value: &str) -> String {
    let needs_quote = value.is_empty()
        || value.starts_with(' ')
        || value.ends_with(' ')
        || value.contains(':')
        || value.contains('#')
        || value.contains('"')
        || value.contains('\n')
        || value.parse::<f64>().is_ok()
        || matches!(
            value.to_lowercase().as_str(),
            "true" | "false" | "null" | "yes" | "no" | "on" | "off" | "~"
        );
    if needs_quote {
        format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
    } else {
        value.to_string()
    }
}

pub(crate) fn escape_label(text: &str) -> String {
    text.replace('[', "\\[").replace(']', "\\]")
}

fn escape_heading_text(text: &str) -> String {
    text.replace('#', "\\#").replace('\n', " ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meta(rel: &str) -> PageMeta {
        PageMeta {
            id: "1".into(),
            title: "Page".into(),
            space_key: "PROD".into(),
            space_name: "Product".into(),
            web_url: "https://t.atlassian.net/wiki/spaces/PROD/pages/1/Page".into(),
            ancestors: vec![],
            homepage_id: None,
            version: 1,
            updated: None,
            rel_path: rel.into(),
        }
    }

    fn index() -> ExportIndex {
        let mut idx = ExportIndex::default();
        idx.base_url = "https://t.atlassian.net".into();
        idx.pages_by_id.insert(
            "2".into(),
            IndexedPage {
                rel_path: "Product/Guide.md".into(),
                web_url: "https://t.atlassian.net/wiki/spaces/PROD/pages/2/Guide".into(),
            },
        );
        idx.page_ids_by_title.insert(("prod".into(), "Guide".into()), "2".into());
        idx
    }

    #[test]
    fn relative_href_between_dirs() {
        assert_eq!(
            relative_href("Product/Docs/Page.md", "Product/Guide.md"),
            "../Guide.md"
        );
        assert_eq!(relative_href("Product/Page.md", "Product/Guide.md"), "Guide.md");
        assert_eq!(
            relative_href("Product/Page.md", "Eng/Guide.md"),
            "../Eng/Guide.md"
        );
    }

    #[test]
    fn yaml_quotes_specials() {
        assert_eq!(yaml_scalar("plain"), "plain");
        assert_eq!(yaml_scalar("a: b"), "\"a: b\"");
        assert_eq!(yaml_scalar(""), "\"\"");
        assert_eq!(yaml_scalar("true"), "\"true\"");
    }

    #[test]
    fn converts_simple_paragraph() {
        let out = convert_page(
            &meta("Product/Page.md"),
            "<p>Hello <strong>world</strong></p>",
            &index(),
            &ConvertOptions {
                page_link: HrefMode::Relative,
                attachment_link: HrefMode::Relative,
                include_document_title: false,
                page_breadcrumbs: false,
                page_properties_as_front_matter: true,
                front_matter_standard: false,
            },
        );
        assert!(out.contains("Hello **world**"), "got: {out}");
    }

    fn full_options() -> ConvertOptions {
        ConvertOptions {
            page_link: HrefMode::Relative,
            attachment_link: HrefMode::Relative,
            include_document_title: false,
            page_breadcrumbs: false,
            page_properties_as_front_matter: true,
            front_matter_standard: false,
        }
    }

    #[test]
    fn converts_code_macro_with_language_and_cdata() {
        let storage = r#"<ac:structured-macro ac:name="code" ac:schema-version="1">
            <ac:parameter ac:name="language">python</ac:parameter>
            <ac:plain-text-body><![CDATA[def hello():
    print("hi <world>")]]></ac:plain-text-body>
        </ac:structured-macro>"#;
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.contains("```python"), "got: {out}");
        assert!(out.contains("def hello():"), "got: {out}");
        assert!(out.contains("print(\"hi <world>\")"), "got: {out}");
    }

    #[test]
    fn converts_info_panel_and_task_list() {
        let storage = concat!(
            r#"<ac:structured-macro ac:name="info"><ac:rich-text-body><p>알아두기</p></ac:rich-text-body></ac:structured-macro>"#,
            r#"<ac:task-list><ac:task><ac:task-id>1</ac:task-id><ac:task-status>complete</ac:task-status><ac:task-body>완료 항목</ac:task-body></ac:task>"#,
            r#"<ac:task><ac:task-id>2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>할 일</ac:task-body></ac:task></ac:task-list>"#
        );
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.contains("> **[정보]**"), "got: {out}");
        assert!(out.contains("> 알아두기"), "got: {out}");
        assert!(out.contains("- [x] 완료 항목"), "got: {out}");
        assert!(out.contains("- [ ] 할 일"), "got: {out}");
    }

    #[test]
    fn converts_table_with_alignment() {
        let storage = "<table><thead><tr><th>이름</th><th style=\"text-align: center;\">값</th></tr></thead><tbody><tr><td>a</td><td style=\"text-align: center;\">1</td></tr></tbody></table>";
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.contains("| 이름 | 값 |"), "got: {out}");
        assert!(out.contains("| --- | :---: |"), "got: {out}");
        assert!(out.contains("| a | 1 |"), "got: {out}");
    }

    #[test]
    fn resolves_page_links_by_mode() {
        let storage = r#"<p><ac:link><ri:page ri:content-title="Guide" ri:space-key="PROD"/><ac:plain-text-link-body><![CDATA[가이드 문서]]></ac:plain-text-link-body></ac:link></p>"#;
        let relative = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(relative.contains("[가이드 문서](Guide.md)"), "got: {relative}");

        let wiki_options = ConvertOptions { page_link: HrefMode::Wiki, ..full_options() };
        let wiki = convert_page(&meta("Product/Page.md"), storage, &index(), &wiki_options);
        assert!(wiki.contains("https://t.atlassian.net/wiki/spaces/PROD/pages/2/Guide"), "got: {wiki}");
    }

    #[test]
    fn page_properties_become_front_matter() {
        let storage = r#"<ac:structured-macro ac:name="page-properties"><ac:rich-text-body><table><tbody>
            <tr><td>담당자</td><td>홍길동</td></tr>
            <tr><td>상태</td><td>검토 중</td></tr>
        </tbody></table></ac:rich-text-body></ac:structured-macro><p>본문</p>"#;
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.starts_with("---\n"), "got: {out}");
        assert!(out.contains("담당자: 홍길동"), "got: {out}");
        assert!(out.contains("상태: 검토 중"), "got: {out}");
        assert!(out.contains("본문"), "got: {out}");
    }

    #[test]
    fn expand_macro_becomes_details() {
        let storage = r#"<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">자세히</ac:parameter><ac:rich-text-body><p>숨김 내용</p></ac:rich-text-body></ac:structured-macro>"#;
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.contains("<details>"), "got: {out}");
        assert!(out.contains("<summary>자세히</summary>"), "got: {out}");
        assert!(out.contains("숨김 내용"), "got: {out}");
    }

    #[test]
    fn unsupported_macro_falls_back_to_comment() {
        let storage = r#"<ac:structured-macro ac:name="drawio"><ac:rich-text-body><p>diagram</p></ac:rich-text-body></ac:structured-macro>"#;
        let out = convert_page(&meta("Product/Page.md"), storage, &index(), &full_options());
        assert!(out.contains("<!-- 지원되지 않는 매크로: drawio -->"), "got: {out}");
    }

    #[test]
    fn attachment_image_resolves_relative_href() {
        let mut idx = index();
        idx.attachments_by_file_id.insert(
            "f1".into(),
            IndexedAttachment { rel_path: "Product/attachments/f1.png".into(), title: "shot.png".into(), page_id: "1".into() },
        );
        idx.attachment_ids_by_title.insert("shot.png".into(), "f1".into());
        let storage = r#"<p><ac:image ac:alt="스크린샷"><ri:attachment ri:filename="shot.png"/></ac:image></p>"#;
        let out = convert_page(&meta("Product/Page.md"), storage, &idx, &full_options());
        assert!(out.contains("![스크린샷](attachments/f1.png)"), "got: {out}");
    }

    #[test]
    fn standard_front_matter_includes_metadata() {
        let options = ConvertOptions { front_matter_standard: true, ..full_options() };
        let out = convert_page(&meta("Product/Page.md"), "<p>x</p>", &index(), &options);
        assert!(out.contains("title: Page"), "got: {out}");
        assert!(out.contains("space: PROD"), "got: {out}");
        assert!(out.contains("version: 1"), "got: {out}");
        assert!(out.contains("url: \"https://t.atlassian.net/wiki/spaces/PROD/pages/1/Page\""), "got: {out}");
    }

    #[test]
    fn breadcrumbs_render_space_and_ancestors() {
        let mut page = meta("Product/Docs/Page.md");
        page.ancestors = vec![
            AncestorLink { id: "9".into(), title: "Home".into() },
            AncestorLink { id: "10".into(), title: "Docs".into() },
        ];
        page.homepage_id = Some("9".into());
        let options = ConvertOptions { page_breadcrumbs: true, ..full_options() };
        let out = convert_page(&page, "<p>x</p>", &index(), &options);
        assert!(out.contains("[Product](https://t.atlassian.net/wiki/spaces/PROD)"), "got: {out}");
        assert!(out.contains("[Docs]("), "got: {out}");
        assert!(!out.contains("[Home]("), "homepage must be excluded from ancestors: {out}");
        assert!(out.contains("**Page**"), "got: {out}");
    }
}
