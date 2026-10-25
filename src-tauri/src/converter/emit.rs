//! Storage-format tree walker that emits Markdown.

use super::tree::Nd;
use super::{ConvertOptions, ExportIndex, PageMeta, escape_label, file_href};

pub(crate) struct BodyOut {
    pub markdown: String,
    pub properties: Vec<(String, String)>,
}

pub(crate) fn emit_body(
    body: &Nd,
    page: &PageMeta,
    index: &ExportIndex,
    opts: &ConvertOptions,
) -> BodyOut {
    let ctx = Ctx { page, index, opts };
    let mut properties = Vec::new();
    let markdown = ctx.blocks(body.children(), &mut properties);
    BodyOut { markdown, properties }
}

struct Ctx<'a> {
    page: &'a PageMeta,
    index: &'a ExportIndex,
    opts: &'a ConvertOptions,
}

const INLINE_TAGS: &[&str] = &[
    "a", "b", "strong", "i", "em", "u", "ins", "s", "del", "strike", "code", "tt", "span",
    "sup", "sub", "br", "img", "time", "abbr", "cite", "q", "mark", "small", "big", "font",
    "ac:link", "ac:image", "ac:emoji", "ac:tag", "ri:user",
];

impl Ctx<'_> {
    // ---------- block layer ----------

    fn blocks(&self, nodes: &[Nd], properties: &mut Vec<(String, String)>) -> String {
        let mut parts: Vec<String> = Vec::new();
        for node in nodes {
            if let Some(block) = self.block(node, properties) {
                let block = block.trim().to_string();
                if !block.is_empty() {
                    parts.push(block);
                }
            }
        }
        parts.join("\n\n")
    }

    fn block(&self, node: &Nd, properties: &mut Vec<(String, String)>) -> Option<String> {
        let name = match node.name() {
            Some(name) => name,
            None => return None, // text/comment directly under a block container
        };
        match name {
            "h1" | "h2" | "h3" | "h4" | "h5" | "h6" => {
                let level = name[1..].parse::<usize>().unwrap_or(1);
                let text = self.inline_children(node.children()).trim().to_string();
                if text.is_empty() {
                    None
                } else {
                    Some(format!("{} {}", "#".repeat(level.clamp(1, 6)), text))
                }
            }
            "p" => self.paragraph(node),
            "ul" | "ol" => Some(self.list(node, 0)),
            "ac:task-list" => Some(self.task_list(node, 0)),
            "table" => self.table(node),
            "blockquote" => {
                let inner = self.blocks(node.children(), properties);
                if inner.is_empty() {
                    None
                } else {
                    Some(inner.lines().map(|line| {
                        if line.trim().is_empty() { ">".to_string() } else { format!("> {line}") }
                    }).collect::<Vec<_>>().join("\n"))
                }
            }
            "pre" => {
                let text = node.direct_text();
                if text.trim().is_empty() { None } else { Some(fence_block(&text, None)) }
            }
            "hr" => Some("---".to_string()),
            "div" => {
                if node.has_class("confluence-information-macro") {
                    return Some(self.panel(
                        node,
                        macro_kind_from_classes(node.attr("class").unwrap_or_default()),
                        self.panel_div_title(node),
                    ));
                }
                let inner = self.blocks(node.children(), properties);
                if inner.is_empty() { None } else { Some(inner) }
            }
            "ac:structured-macro" => self.structured_macro(node, properties),
            "dl" => self.definition_list(node),
            "figure" => {
                let mut parts = Vec::new();
                let mut caption: Option<String> = None;
                for child in node.children() {
                    match child.name() {
                        Some("figcaption") => {
                            let text = self.inline_children(child.children()).trim().to_string();
                            if !text.is_empty() {
                                caption = Some(format!("*{text}*"));
                            }
                        }
                        _ => {
                            if let Some(block) = self.block(child, properties) {
                                parts.push(block);
                            }
                        }
                    }
                }
                if let Some(caption) = caption {
                    parts.push(caption);
                }
                if parts.is_empty() { None } else { Some(parts.join("\n\n")) }
            }
            other if INLINE_TAGS.contains(&other) => {
                // an inline element at block level renders as its own paragraph
                let text = self.inline(node);
                let text = text.trim().to_string();
                if text.is_empty() { None } else { Some(text) }
            }
            _ => {
                let inner = self.blocks(node.children(), properties);
                if inner.is_empty() { None } else { Some(inner) }
            }
        }
    }

    fn paragraph(&self, node: &Nd) -> Option<String> {
        let text = self.inline_children(node.children()).trim().to_string();
        if text.is_empty() {
            None
        } else {
            Some(escape_leading_marker(&text))
        }
    }

    fn panel_div_title(&self, node: &Nd) -> Option<String> {
        for child in node.children() {
            if child.has_class("confluence-information-macro-heading") {
                let text = self.inline_children(child.children()).trim().to_string();
                if !text.is_empty() {
                    return Some(text);
                }
            }
        }
        None
    }

    fn panel(&self, node: &Nd, kind: PanelKind, title: Option<String>) -> String {
        let label = match kind {
            PanelKind::Info => "정보",
            PanelKind::Note => "메모",
            PanelKind::Warning => "주의",
            PanelKind::Tip => "팁",
            PanelKind::Plain => "패널",
        };
        let mut body_nodes: Vec<&Nd> = Vec::new();
        for child in node.children() {
            if child.has_class("confluence-information-macro-heading") {
                continue;
            }
            body_nodes.push(child);
        }
        let owned: Vec<Nd> = body_nodes.into_iter().cloned().collect();
        let mut sink = Vec::new();
        let inner = self.blocks(&owned, &mut sink);
        let mut lines: Vec<String> = Vec::new();
        let header = match &title {
            Some(title) => format!("> **[{label}] {title}**"),
            None => format!("> **[{label}]**"),
        };
        lines.push(header);
        if !inner.is_empty() {
            lines.push(">".to_string());
            for line in inner.lines() {
                lines.push(if line.trim().is_empty() { ">".to_string() } else { format!("> {line}") });
            }
        }
        lines.join("\n")
    }

    fn list(&self, node: &Nd, depth: usize) -> String {
        let ordered = node.name() == Some("ol");
        let start: usize = node.attr("start").and_then(|s| s.parse().ok()).unwrap_or(1);
        let mut lines: Vec<String> = Vec::new();
        for (idx, item) in node.element_children().enumerate() {
            if item.name() == Some("li") {
                let marker = if ordered {
                    format!("{}. ", start + idx)
                } else {
                    "- ".to_string()
                };
                lines.push(self.list_item(item, &marker, depth));
            } else if matches!(item.name(), Some("ul") | Some("ol") | Some("ac:task-list")) {
                // list nested directly without an <li> wrapper
                let nested = match item.name() {
                    Some("ac:task-list") => self.task_list(item, depth + 1),
                    _ => self.list(item, depth + 1),
                };
                lines.push(nested);
            }
        }
        lines.join("\n")
    }

    fn list_item(&self, li: &Nd, marker: &str, depth: usize) -> String {
        let indent = "  ".repeat(depth);
        let mut main = String::new();
        let mut nested: Vec<String> = Vec::new();
        for child in li.children() {
            match child.name() {
                Some("ul") => nested.push(self.list(child, depth + 1)),
                Some("ol") => nested.push(self.list(child, depth + 1)),
                Some("ac:task-list") => nested.push(self.task_list(child, depth + 1)),
                Some("p") => {
                    let text = self.inline_children(child.children());
                    if !text.trim().is_empty() {
                        if !main.is_empty() {
                            main.push('\n');
                        }
                        main.push_str(text.trim());
                    }
                }
                None => {
                    let text = self.inline(child);
                    main.push_str(&text);
                }
                _ => {
                    let text = self.inline(child);
                    main.push_str(&text);
                }
            }
        }
        let main = escape_leading_marker(main.trim());
        let mut lines: Vec<String> = Vec::new();
        if main.is_empty() {
            lines.push(format!("{indent}{marker}_"));
        } else {
            for (i, line) in main.lines().enumerate() {
                if i == 0 {
                    lines.push(format!("{indent}{marker}{line}"));
                } else {
                    let pad = " ".repeat(marker.len());
                    lines.push(format!("{indent}{pad}{line}"));
                }
            }
        }
        for nested_block in nested {
            for line in nested_block.lines() {
                lines.push(format!("{indent}  {line}"));
            }
        }
        lines.join("\n")
    }

    fn task_list(&self, node: &Nd, depth: usize) -> String {
        let indent = "  ".repeat(depth);
        let mut lines = Vec::new();
        for task in node.element_children() {
            if task.name() != Some("ac:task") {
                continue;
            }
            let mut done = false;
            let mut body = String::new();
            for child in task.element_children() {
                match child.name() {
                    Some("ac:task-status") => done = child.direct_text().trim() == "complete",
                    Some("ac:task-body") => body = self.inline_children(child.children()).trim().to_string(),
                    _ => {}
                }
            }
            let checkbox = if done { "[x]" } else { "[ ]" };
            lines.push(format!("{indent}- {checkbox} {body}"));
        }
        lines.join("\n")
    }

    fn table(&self, node: &Nd) -> Option<String> {
        let mut rows: Vec<Vec<&Nd>> = Vec::new();
        let mut header_rows: usize = 0;
        fn collect_row<'a>(tr: &'a Nd, rows: &mut Vec<Vec<&'a Nd>>) {
            let cells: Vec<&Nd> = tr.element_children().filter(|c| matches!(c.name(), Some("th") | Some("td"))).collect();
            if !cells.is_empty() {
                rows.push(cells);
            }
        }
        for child in node.element_children() {
            match child.name() {
                Some("thead") => {
                    for tr in child.element_children() {
                        if tr.name() == Some("tr") {
                            collect_row(tr, &mut rows);
                            header_rows += 1;
                        }
                    }
                }
                Some("tbody") | Some("tfoot") => {
                    for tr in child.element_children() {
                        if tr.name() == Some("tr") {
                            collect_row(tr, &mut rows);
                        }
                    }
                }
                Some("tr") => collect_row(child, &mut rows),
                Some("caption") => {}
                Some("colgroup") | Some("col") => {}
                _ => {}
            }
        }
        if rows.is_empty() {
            return None;
        }
        if header_rows == 0 && rows[0].iter().all(|c| c.name() == Some("th")) {
            header_rows = 1;
        }
        let has_span = rows.iter().flatten().any(|cell| {
            cell.attr("colspan").map(|v| v != "1").unwrap_or(false)
                || cell.attr("rowspan").map(|v| v != "1").unwrap_or(false)
        });
        if has_span {
            return Some(self.html_table(&rows, header_rows));
        }
        let cell_text = |cell: &Nd| -> String {
            let text = self.inline_children(cell.children());
            text.trim().replace('|', "\\|").replace('\n', "<br>")
        };
        let align_of = |cell: &Nd| -> char {
            let style = cell.attr("style").unwrap_or_default();
            if style.contains("center") {
                'c'
            } else if style.contains("right") {
                'r'
            } else {
                'l'
            }
        };
        let mut out: Vec<String> = Vec::new();
        let width = rows.iter().map(|r| r.len()).max().unwrap_or(0);
        let render_row = |cells: &[&Nd]| -> String {
            let mut parts: Vec<String> = Vec::with_capacity(width);
            for i in 0..width {
                let text = cells.get(i).map(|c| cell_text(c)).unwrap_or_default();
                parts.push(text);
            }
            format!("| {} |", parts.join(" | "))
        };
        let (header, body): (Vec<Vec<&Nd>>, Vec<Vec<&Nd>>) = if header_rows > 0 {
            (rows[..header_rows].to_vec(), rows[header_rows..].to_vec())
        } else {
            (vec![rows[0].clone()], rows[1..].to_vec())
        };
        for row in &header {
            out.push(render_row(row));
        }
        let alignment: Vec<char> = (0..width)
            .map(|i| header.first().and_then(|r| r.get(i).copied()).map(align_of).unwrap_or('l'))
            .collect();
        let align_row: String = alignment
            .iter()
            .map(|a| match a {
                'c' => ":---:",
                'r' => "---:",
                _ => "---",
            })
            .collect::<Vec<_>>()
            .join(" | ");
        out.push(format!("| {align_row} |"));
        if header_rows == 0 && body.is_empty() {
            // header-only table with no explicit body: nothing more to render
        }
        for row in &body {
            out.push(render_row(row));
        }
        Some(out.join("\n"))
    }

    fn html_table(&self, rows: &[Vec<&Nd>], header_rows: usize) -> String {
        let escape_html = |text: &str| -> String {
            text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
        };
        let render_cell = |cell: &Nd, tag: &str| -> String {
            let mut attrs = String::new();
            if let Some(colspan) = cell.attr("colspan") {
                if colspan != "1" {
                    attrs.push_str(&format!(" colspan=\"{colspan}\""));
                }
            }
            if let Some(rowspan) = cell.attr("rowspan") {
                if rowspan != "1" {
                    attrs.push_str(&format!(" rowspan=\"{rowspan}\""));
                }
            }
            format!("<{tag}{attrs}>{}</{tag}>", escape_html(&cell.direct_text().trim()))
        };
        let mut out = String::from("<table>");
        for (idx, row) in rows.iter().enumerate() {
            out.push_str("<tr>");
            for cell in row {
                let tag = if idx < header_rows.max(1) || cell.name() == Some("th") { "th" } else { "td" };
                out.push_str(&render_cell(cell, tag));
            }
            out.push_str("</tr>");
        }
        out.push_str("</table>");
        out
    }

    fn definition_list(&self, node: &Nd) -> Option<String> {
        let mut parts: Vec<String> = Vec::new();
        let mut pending_term: Option<String> = None;
        for child in node.element_children() {
            match child.name() {
                Some("dt") => {
                    if let Some(term) = pending_term.take() {
                        parts.push(format!("**{term}**"));
                    }
                    let text = self.inline_children(child.children()).trim().to_string();
                    if !text.is_empty() {
                        pending_term = Some(text);
                    }
                }
                Some("dd") => {
                    let text = self.inline_children(child.children()).trim().to_string();
                    match pending_term.take() {
                        Some(term) if !text.is_empty() => parts.push(format!("**{term}** — {text}")),
                        Some(term) => parts.push(format!("**{term}**")),
                        None if !text.is_empty() => parts.push(text),
                        None => {}
                    }
                }
                _ => {}
            }
        }
        if let Some(term) = pending_term {
            parts.push(format!("**{term}**"));
        }
        if parts.is_empty() { None } else { Some(parts.join("\n\n")) }
    }

    // ---------- macros ----------

    fn structured_macro(&self, node: &Nd, properties: &mut Vec<(String, String)>) -> Option<String> {
        let name = node.attr("ac:name").unwrap_or_default();
        match name {
            "code" | "noformat" => {
                let language = if name == "noformat" {
                    None
                } else {
                    self.macro_param(node, "language")
                };
                let body = node
                    .element_children()
                    .find(|c| c.name() == Some("ac:plain-text-body"))
                    .map(|c| c.direct_text())
                    .unwrap_or_default();
                if body.trim().is_empty() && language.is_none() {
                    return None;
                }
                Some(fence_block(&body, language.as_deref()))
            }
            "info" | "note" | "warning" | "tip" | "panel" => {
                let kind = match name {
                    "info" => PanelKind::Info,
                    "note" => PanelKind::Note,
                    "warning" => PanelKind::Warning,
                    "tip" => PanelKind::Tip,
                    _ => PanelKind::Plain,
                };
                let title = self.macro_param(node, "title");
                Some(self.panel(node, kind, title))
            }
            "expand" => {
                let title = self.macro_param(node, "title").unwrap_or_else(|| "펼치기".into());
                let body_nodes: Vec<Nd> = node
                    .element_children()
                    .find(|c| c.name() == Some("ac:rich-text-body"))
                    .map(|b| b.children().to_vec())
                    .unwrap_or_default();
                let inner = self.blocks(&body_nodes, properties);
                Some(format!(
                    "<details>\n<summary>{}</summary>\n\n{}\n\n</details>",
                    title.replace('<', "&lt;"),
                    inner
                ))
            }
            "page-properties" => {
                let body = node
                    .element_children()
                    .find(|c| c.name() == Some("ac:rich-text-body"));
                match body {
                    Some(body) if self.opts.page_properties_as_front_matter => {
                        self.extract_properties(body, properties);
                        None
                    }
                    Some(body) => self.blocks(body.children(), properties).into_option(),
                    None => None,
                }
            }
            "page-properties-report" | "toc" | "toc-zone" | "children" | "info-in-macro" => None,
            "jira" | "jiraissues" => {
                let key = self
                    .macro_param(node, "key")
                    .or_else(|| self.macro_param(node, "jql"))
                    .unwrap_or_else(|| "Jira".into());
                match self.macro_param(node, "server") {
                    Some(server) => Some(format!("[Jira: {key}]({}/browse/{key})", server.trim_end_matches('/'))),
                    None => Some(format!("[Jira: {key}]")),
                }
            }
            "date" => {
                let value = self.macro_param(node, "value").unwrap_or_default();
                if value.is_empty() { None } else { Some(value) }
            }
            "status" => {
                let title = self.macro_param(node, "title").unwrap_or_default();
                let color = self.macro_param(node, "colour").unwrap_or_default();
                if title.is_empty() { None } else { Some(format!("`{title}` ({color})")) }
            }
            _ => Some(format!("<!-- 지원되지 않는 매크로: {name} -->")),
        }
    }

    fn macro_param(&self, node: &Nd, key: &str) -> Option<String> {
        node.element_children()
            .find(|c| c.name() == Some("ac:parameter") && c.attr("ac:name") == Some(key))
            .map(|c| c.direct_text().trim().to_string())
            .filter(|v| !v.is_empty())
    }

    fn extract_properties(&self, body: &Nd, properties: &mut Vec<(String, String)>) {
        for table in body.element_children().filter(|c| c.name() == Some("table")) {
            // rows may sit directly under <table> or inside <thead>/<tbody>
            let mut rows: Vec<&Nd> = Vec::new();
            for child in table.element_children() {
                match child.name() {
                    Some("tr") => rows.push(child),
                    Some("thead") | Some("tbody") | Some("tfoot") => {
                        rows.extend(child.element_children().filter(|c| c.name() == Some("tr")));
                    }
                    _ => {}
                }
            }
            for tr in rows {
                let cells: Vec<&Nd> = tr
                    .element_children()
                    .filter(|c| matches!(c.name(), Some("td") | Some("th")))
                    .collect();
                if cells.len() < 2 {
                    continue;
                }
                let key = clean_plain(&cells[0].direct_text());
                if key.is_empty() {
                    continue;
                }
                let value = cells[1..]
                    .iter()
                    .map(|c| clean_plain(&c.direct_text()))
                    .filter(|v| !v.is_empty())
                    .collect::<Vec<_>>()
                    .join(", ");
                properties.push((key, value));
            }
        }
    }

    // ---------- inline layer ----------

    fn inline_children(&self, children: &[Nd]) -> String {
        let mut out = String::new();
        for child in children {
            out.push_str(&self.inline(child));
        }
        out
    }

    fn inline(&self, node: &Nd) -> String {
        match node {
            Nd::Text(text) => escape_inline(&collapse_ws(text)),
            Nd::Comment(_) => String::new(),
            Nd::El { .. } => match node.name().unwrap_or_default() {
                "br" => "  \n".to_string(),
                "strong" | "b" => self.wrap_inline(node, "**"),
                "em" | "i" | "cite" => self.wrap_inline(node, "*"),
                "del" | "s" | "strike" => self.wrap_inline(node, "~~"),
                "code" | "tt" => {
                    let raw = node.direct_text();
                    let raw = raw.trim();
                    if raw.is_empty() {
                        String::new()
                    } else if raw.contains('`') {
                        format!("`` {raw} ``")
                    } else {
                        format!("`{raw}`")
                    }
                }
                "u" | "ins" | "sup" | "sub" => {
                    let tag = match node.name().unwrap_or_default() {
                        "sup" => "sup",
                        "sub" => "sub",
                        _ => "u",
                    };
                    let text = escape_html(&node.direct_text());
                    if text.is_empty() { String::new() } else { format!("<{tag}>{text}</{tag}>") }
                }
                "a" => self.anchor_link(node),
                "ac:link" => self.ac_link(node),
                "ac:image" => self.image(node.attr("ac:alt"), Some(node), None),
                "img" => self.image(node.attr("alt"), None, Some(node.attr("src").unwrap_or_default())),
                "span" | "font" | "mark" | "small" | "abbr" => self.inline_children(node.children()),
                "time" => {
                    let text = clean_plain(&node.direct_text());
                    if text.is_empty() {
                        node.attr("datetime").unwrap_or_default().to_string()
                    } else {
                        text
                    }
                }
                "ri:user" => format!("@{}", node.attr("ri:username").unwrap_or("user")),
                "ac:emoji" => node
                    .attr("ac:shortname")
                    .or_else(|| node.attr("ri:shortcut"))
                    .unwrap_or(":)")
                    .to_string(),
                "ac:placeholder" => String::new(),
                "p" => {
                    // block element met in inline context: hard break + content
                    let inner = self.inline_children(node.children());
                    if inner.trim().is_empty() { String::new() } else { format!("\n{}", inner.trim()) }
                }
                _ => self.inline_children(node.children()),
            },
        }
    }

    fn wrap_inline(&self, node: &Nd, marker: &str) -> String {
        let content = self.inline_children(node.children());
        let content = content.trim();
        if content.is_empty() {
            String::new()
        } else {
            format!("{marker}{content}{marker}")
        }
    }

    fn anchor_link(&self, node: &Nd) -> String {
        let text = self.inline_children(node.children());
        let text = if text.trim().is_empty() {
            String::new()
        } else {
            text.trim().to_string()
        };
        let href = match node.attr("href") {
            Some(href) if !href.trim().is_empty() => href.trim(),
            _ => return text,
        };
        let resolved = if href.starts_with('/') {
            format!("{}/wiki{}", self.index.base_url.trim_end_matches('/'), href)
        } else {
            href.to_string()
        };
        if text.is_empty() {
            return format!("<{}>", resolved.replace('<', "%3C"));
        }
        format!("[{}]({})", text, wrap_href(&resolved))
    }

    fn ac_link(&self, node: &Nd) -> String {
        let anchor = node.attr("ac:anchor").map(str::to_string);
        let mut target: Option<Target<'_>> = None;
        for child in node.element_children() {
            match child.name() {
                Some("ri:page") => {
                    target = Some(Target::Page {
                        title: child.attr("ri:content-title").unwrap_or_default(),
                        space_key: child.attr("ri:space-key").map(str::to_string),
                    });
                    break;
                }
                Some("ri:attachment") => {
                    target = Some(Target::Attachment {
                        filename: child.attr("ri:filename").unwrap_or_default(),
                    });
                    break;
                }
                Some("ri:url") => {
                    target = Some(Target::Url { url: child.attr("ri:value").unwrap_or_default() });
                    break;
                }
                Some("ri:user") => {
                    return format!("@{}", child.attr("ri:username").unwrap_or("user"));
                }
                _ => {}
            }
        }
        let body_text = node
            .element_children()
            .find(|c| matches!(c.name(), Some("ac:plain-text-link-body") | Some("ac:link-body")))
            .map(|c| {
                if c.name() == Some("ac:plain-text-link-body") {
                    c.direct_text()
                } else {
                    self.inline_children(c.children())
                }
            })
            .map(|t| t.trim().to_string())
            .unwrap_or_default();

        let (href, default_text) = match target {
            Some(Target::Page { title, space_key }) => {
                let space = space_key.unwrap_or_else(|| self.page.space_key.clone());
                let text = if body_text.is_empty() { title.to_string() } else { body_text.clone() };
                if title.is_empty() {
                    return text;
                }
                if let Some(indexed) = self.index.lookup_page(&space, title) {
                    (
                        file_href(
                            self.opts.page_link,
                            &indexed.rel_path,
                            &self.page.rel_path,
                            &indexed.web_url,
                        ),
                        text,
                    )
                } else if let Some(url) = self.index.external_page_url(&space, title) {
                    (url, text)
                } else {
                    return text;
                }
            }
            Some(Target::Attachment { filename }) => {
                let text = if body_text.is_empty() { filename.to_string() } else { body_text.clone() };
                match self.index.lookup_attachment(filename) {
                    Some(att) => (
                        file_href(
                            self.opts.attachment_link,
                            &att.rel_path,
                            &self.page.rel_path,
                            &self.index.attachment_web_url(att),
                        ),
                        text,
                    ),
                    None => return text,
                }
            }
            Some(Target::Url { url }) => {
                let text = if body_text.is_empty() { url.to_string() } else { body_text.clone() };
                (url.to_string(), text)
            }
            None => {
                // anchor-only link within the same page
                let text = body_text.clone();
                let anchor = anchor.clone().unwrap_or_default();
                if anchor.is_empty() {
                    return text;
                }
                (format!("#{}", slug(&anchor)), text)
            }
        };

        if href.is_empty() {
            return default_text;
        }
        let mut href = href;
        if let Some(anchor) = anchor {
            if !anchor.is_empty() && !href.starts_with('#') {
                href = format!("{href}#{}", slug(&anchor));
            }
        }
        if default_text.is_empty() {
            return format!("<{}>", href.replace('<', "%3C"));
        }
        format!("[{}]({})", escape_label(&default_text), wrap_href(&href))
    }

    fn image(&self, alt: Option<&str>, container: Option<&Nd>, src: Option<&str>) -> String {
        let mut alt_text: Option<String> = alt
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());
        let mut resolved_src = String::new();
        let mut width: Option<String> = None;
        if let Some(node) = container {
            for child in node.element_children() {
                match child.name() {
                    Some("ri:attachment") => {
                        let filename = child.attr("ri:filename").unwrap_or_default();
                        if let Some(att) = self.index.lookup_attachment(filename) {
                            resolved_src = file_href(
                                self.opts.attachment_link,
                                &att.rel_path,
                                &self.page.rel_path,
                                &self.index.attachment_web_url(att),
                            );
                        }
                    }
                    Some("ri:url") => {
                        resolved_src = child.attr("ri:value").unwrap_or_default().to_string();
                    }
                    _ => {}
                }
            }
            for child in node.element_children() {
                if child.name() == Some("ac:parameter") {
                    match child.attr("ac:name") {
                        Some("width") => width = Some(clean_plain(&child.direct_text())),
                        Some("alt") => {
                            if alt_text.is_none() {
                                alt_text = Some(clean_plain(&child.direct_text()));
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
        if resolved_src.is_empty() {
            if let Some(src) = src {
                resolved_src = src.to_string();
            }
        }
        if resolved_src.is_empty() {
            return alt_text.unwrap_or_default();
        }
        let alt_value = alt_text.unwrap_or_default().replace('[', "\\[").replace(']', "\\]");
        let width = width
            .map(|w| w.trim_end_matches("px").to_string())
            .filter(|w| !w.is_empty());
        match width {
            Some(width) => format!(
                "<img src=\"{}\" alt=\"{}\" width=\"{}\" />",
                resolved_src.replace('"', "%22"),
                alt_value.replace('"', "&quot;"),
                width
            ),
            None => format!("![{}]({})", alt_value, wrap_href(&resolved_src)),
        }
    }
}

enum Target<'a> {
    Page { title: &'a str, space_key: Option<String> },
    Attachment { filename: &'a str },
    Url { url: &'a str },
}

enum PanelKind {
    Info,
    Note,
    Warning,
    Tip,
    Plain,
}

fn macro_kind_from_classes(classes: &str) -> PanelKind {
    for class in classes.split_whitespace() {
        if class.ends_with("-information") {
            return PanelKind::Info;
        }
        if class.ends_with("-note") {
            return PanelKind::Note;
        }
        if class.ends_with("-warning") {
            return PanelKind::Warning;
        }
        if class.ends_with("-tip") {
            return PanelKind::Tip;
        }
    }
    PanelKind::Plain
}

// ---------- text utilities ----------

fn collapse_ws(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut last_ws = false;
    for ch in text.chars() {
        if ch == '\n' || ch == '\r' || ch == '\t' || ch == ' ' {
            if !last_ws {
                out.push(' ');
            }
            last_ws = true;
        } else {
            out.push(ch);
            last_ws = false;
        }
    }
    out
}

fn escape_inline(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let chars: Vec<char> = text.chars().collect();
    for (idx, ch) in chars.iter().enumerate() {
        match ch {
            '\\' | '`' | '*' | '_' | '[' | ']' => {
                out.push('\\');
                out.push(*ch);
            }
            '<' => out.push_str("&lt;"),
            '&' => out.push_str("&amp;"),
            '!' if chars.get(idx + 1) == Some(&'[') => {
                out.push_str("\\!");
            }
            _ => out.push(*ch),
        }
    }
    out
}

fn escape_html(text: &str) -> String {
    text.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}

fn escape_leading_marker(text: &str) -> String {
    let trimmed = text.trim_start();
    let needs_escape = trimmed.starts_with('#')
        || trimmed.starts_with('>')
        || trimmed.starts_with('-')
        || trimmed.starts_with('+')
        || trimmed.starts_with("1. ")
        || trimmed.starts_with("= ");
    if needs_escape && !text.starts_with('\\') {
        let mut out = String::from("\\");
        out.push_str(text);
        out
    } else {
        text.to_string()
    }
}

fn clean_plain(text: &str) -> String {
    collapse_ws(text).trim().to_string()
}

fn fence_block(content: &str, language: Option<&str>) -> String {
    let content = content.strip_suffix('\n').unwrap_or(content);
    let mut max_run = 0usize;
    let mut current = 0usize;
    for ch in content.chars() {
        if ch == '`' {
            current += 1;
            max_run = max_run.max(current);
        } else {
            current = 0;
        }
    }
    let fence_len = 3.max(max_run + 1);
    let fence = "`".repeat(fence_len);
    match language {
        Some(lang) if !lang.trim().is_empty() => {
            format!("{fence}{}\n{content}\n{fence}", lang.trim().to_lowercase())
        }
        _ => format!("{fence}\n{content}\n{fence}"),
    }
}

fn wrap_href(href: &str) -> String {
    href.replace(' ', "%20")
        .replace('(', "%28")
        .replace(')', "%29")
        .replace('<', "%3C")
        .replace('>', "%3E")
}

fn slug(text: &str) -> String {
    let mut out = String::new();
    for ch in text.trim().chars() {
        if ch.is_whitespace() {
            out.push('-');
        } else if ch.is_alphanumeric() || ch == '-' || ch == '_' {
            out.push(ch.to_lowercase().next().unwrap_or(ch));
        }
    }
    out
}

trait IntoOption {
    fn into_option(self) -> Option<String>;
}

impl IntoOption for String {
    fn into_option(self) -> Option<String> {
        if self.trim().is_empty() { None } else { Some(self) }
    }
}
