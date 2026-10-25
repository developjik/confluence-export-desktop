//! Output path templating and sanitization.

use std::collections::HashSet;

/// Render `{space_name}/{ancestor_titles}/{page_title}.md`-style templates
/// into a sanitized relative path (forward slashes).
pub struct PagePathCtx<'a> {
    pub space_key: &'a str,
    pub space_name: &'a str,
    pub homepage_title: Option<&'a str>,
    /// Ancestor titles below the homepage, root → parent.
    pub ancestors: Vec<&'a str>,
    pub page_title: &'a str,
}

pub struct AttachmentPathCtx<'a> {
    pub space_key: &'a str,
    pub space_name: &'a str,
    pub page_title: &'a str,
    pub file_id: &'a str,
    pub file_name: &'a str,
    pub extension: &'a str,
}

pub fn render_page_path(template: &str, ctx: &PagePathCtx<'_>, max_segment: usize) -> String {
    let mut segments: Vec<String> = Vec::new();
    for raw in template.split('/') {
        // tokens may carry suffixes (e.g. "{page_title}.md"), so substitute within the segment
        let mut value = raw.to_string();
        value = value.replace("{space_name}", ctx.space_name);
        value = value.replace("{space_key}", ctx.space_key);
        value = value.replace("{homepage_title}", ctx.homepage_title.unwrap_or_default());
        let ancestors = if ctx.ancestors.is_empty() {
            String::new()
        } else {
            ctx.ancestors
                .iter()
                .map(|title| sanitize_segment(title, max_segment))
                .collect::<Vec<_>>()
                .join("/")
        };
        value = value.replace("{ancestor_titles}", &ancestors);
        value = value.replace("{page_title}", ctx.page_title);
        for part in value.split('/') {
            if part.trim().is_empty() {
                continue;
            }
            let sanitized = sanitize_segment(part, max_segment);
            if !sanitized.is_empty() && sanitized != "." {
                segments.push(sanitized);
            }
        }
    }
    ensure_md_extension(&segments.join("/"))
}

pub fn render_attachment_path(template: &str, ctx: &AttachmentPathCtx<'_>, max_segment: usize) -> String {
    let mut segments: Vec<String> = Vec::new();
    for raw in template.split('/') {
        let mut value = raw.to_string();
        value = value.replace("{space_name}", ctx.space_name);
        value = value.replace("{space_key}", ctx.space_key);
        value = value.replace("{page_title}", ctx.page_title);
        value = value.replace("{attachment_file_id}", ctx.file_id);
        value = value.replace("{attachment_file_name}", ctx.file_name);
        value = value.replace("{attachment_title}", ctx.file_name);
        value = value.replace("{attachment_extension}", ctx.extension);
        for part in value.split('/') {
            if part.trim().is_empty() {
                continue;
            }
            let sanitized = sanitize_segment(part, max_segment);
            if !sanitized.is_empty() && sanitized != "." {
                segments.push(sanitized);
            }
        }
    }
    segments.join("/")
}

/// Make sure the final segment ends with `.md` (unless another extension exists).
fn ensure_md_extension(path: &str) -> String {
    if path.is_empty() {
        return "page.md".to_string();
    }
    let last = path.rsplit('/').next().unwrap_or(path);
    if last.contains('.') {
        path.to_string()
    } else {
        format!("{path}.md")
    }
}

const RESERVED: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

/// Sanitize one path segment: replace separators/illegal characters, trim,
/// cap length, and avoid Windows reserved device names.
pub fn sanitize_segment(segment: &str, max_chars: usize) -> String {
    let mut out = String::with_capacity(segment.len());
    for ch in segment.chars() {
        match ch {
            '\\' | '/' | ':' | '*' | '?' | '"' | '<' | '>' | '|' => out.push('_'),
            c if (c as u32) < 0x20 => out.push('_'),
            c => out.push(c),
        }
    }
    let trimmed = out.trim_matches(|c: char| c == '.' || c.is_whitespace());
    let mut result = if trimmed.is_empty() { "_".to_string() } else { trimmed.to_string() };
    if RESERVED.contains(&result.to_uppercase().as_str()) {
        result.push('_');
    }
    truncate_chars(&result, max_chars.max(8))
}

fn truncate_chars(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    let mut out: String = text.chars().take(max_chars).collect();
    while out.ends_with('.') || out.ends_with(' ') {
        out.pop();
    }
    if out.is_empty() {
        out.push('_');
    }
    out
}

/// Allocates unique paths inside one export run by appending `-2`, `-3`, …
/// before the file extension when a path is already taken.
#[derive(Debug, Default)]
pub struct PathAllocator {
    used: HashSet<String>,
}

impl PathAllocator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn allocate(&mut self, path: &str) -> String {
        if self.used.insert(path.to_string()) {
            return path.to_string();
        }
        let (stem, ext) = match path.rfind('.') {
            Some(idx) if !path[idx + 1..].is_empty() && !path[idx + 1..].contains('/') => {
                (&path[..idx], &path[idx..])
            }
            _ => (path, ""),
        };
        for counter in 2..u32::MAX {
            let candidate = format!("{stem}-{counter}{ext}");
            if self.used.insert(candidate.clone()) {
                return candidate;
            }
        }
        unreachable!("path allocator exhausted")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_page_path_with_ancestor_tree() {
        let ctx = PagePathCtx {
            space_key: "PROD",
            space_name: "Product Docs",
            homepage_title: Some("Home"),
            ancestors: vec!["Getting Started", "Setup"],
            page_title: "Install: Windows",
        };
        let path = render_page_path(
            "{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md",
            &ctx,
            120,
        );
        assert_eq!(path, "Product Docs/Home/Getting Started/Setup/Install_ Windows.md");
    }

    #[test]
    fn skips_missing_optional_segments() {
        let ctx = PagePathCtx {
            space_key: "PROD",
            space_name: "Product",
            homepage_title: None,
            ancestors: vec![],
            page_title: "Page",
        };
        let path = render_page_path("{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md", &ctx, 120);
        assert_eq!(path, "Product/Page.md");
    }

    #[test]
    fn sanitizes_reserved_and_trims() {
        assert_eq!(sanitize_segment("CON", 120), "CON_");
        assert_eq!(sanitize_segment("  spaced  ", 120), "spaced");
        assert_eq!(sanitize_section_guard("a/b\\c:d*e?f\"g<h>i|j"), "a_b_c_d_e_f_g_h_i_j");
    }

    fn sanitize_section_guard(input: &str) -> String {
        sanitize_segment(input, 120)
    }

    #[test]
    fn truncates_long_names() {
        let long = "가".repeat(300);
        let out = sanitize_segment(&long, 120);
        assert_eq!(out.chars().count(), 120);
    }

    #[test]
    fn allocates_collisions_with_suffix() {
        let mut alloc = PathAllocator::new();
        assert_eq!(alloc.allocate("a/b.md"), "a/b.md");
        assert_eq!(alloc.allocate("a/b.md"), "a/b-2.md");
        assert_eq!(alloc.allocate("a/b.md"), "a/b-3.md");
        assert_eq!(alloc.allocate("a/b-2.md"), "a/b-2-2.md");
    }
}
