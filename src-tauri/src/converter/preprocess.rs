//! Storage-format preprocessing for HTML5 parsing.
//!
//! Confluence storage format is XML-ish, but the converter parses it with an
//! HTML5 parser. Two XML constructs need normalization first:
//!
//! 1. `<![CDATA[ ... ]]>` — the HTML5 tokenizer treats CDATA as a bogus
//!    comment and drops its content, so it is unwrapped into escaped text.
//! 2. Self-closing foreign elements (`<ri:page ... />`) — HTML5 ignores the
//!    trailing slash and lets following siblings become children, so they are
//!    rewritten as open+close pairs.

/// Normalize a storage-format document for HTML5 parsing.
pub fn preprocess(storage: &str) -> String {
    let without_cdata = unwrap_cdata(storage);
    fix_self_closing(&without_cdata)
}

fn escape_text_body(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for ch in raw.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            _ => out.push(ch),
        }
    }
    out
}

/// Replace `<![CDATA[...]]>` sections with escaped text.
fn unwrap_cdata(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = String::with_capacity(input.len());
    let mut i = 0usize;
    while i < bytes.len() {
        if let Some(start) = input[i..].find("<![CDATA[") {
            let abs_start = i + start;
            out.push_str(&input[i..abs_start]);
            let content_start = abs_start + "<![CDATA[".len();
            match input[content_start..].find("]]>") {
                Some(end_rel) => {
                    let content = &input[content_start..content_start + end_rel];
                    out.push_str(&escape_text_body(content));
                    i = content_start + end_rel + "]]>".len();
                }
                None => {
                    // unterminated CDATA: keep the rest as text
                    out.push_str(&escape_text_body(&input[content_start..]));
                    break;
                }
            }
        } else {
            out.push_str(&input[i..]);
            break;
        }
    }
    out
}

/// Rewrite self-closing `ri:`/`ac:` tags as `<tag ...></tag>`.
fn fix_self_closing(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let chars: Vec<char> = input.chars().collect();
    let n = chars.len();
    let mut i = 0usize;
    while i < n {
        if chars[i] != '<' {
            out.push(chars[i]);
            i += 1;
            continue;
        }
        // find the tag terminator, honoring quoted attribute values
        let mut j = i + 1;
        let mut quote: Option<char> = None;
        while j < n {
            let c = chars[j];
            match quote {
                Some(q) if c == q => quote = None,
                None if c == '"' || c == '\'' => quote = Some(c),
                None if c == '>' => break,
                _ => {}
            }
            j += 1;
        }
        if j >= n {
            out.push_str(&chars[i..].iter().collect::<String>());
            break;
        }
        let tag: String = chars[i..=j].iter().collect();
        let is_self_closing = tag.trim_end().ends_with("/>");
        let name = tag_name(&tag);
        if is_self_closing && (name.starts_with("ri:") || name.starts_with("ac:")) {
            let inner = tag.trim_end();
            let inner = inner[..inner.len() - 2].trim_end();
            out.push_str(inner);
            out.push_str("></");
            out.push_str(name);
            out.push('>');
        } else {
            out.push_str(&tag);
        }
        i = j + 1;
    }
    out
}

fn tag_name(tag: &str) -> &str {
    let body = tag.trim_start_matches('<');
    let end = body.find(|c: char| c.is_whitespace() || c == '/' || c == '>').unwrap_or(body.len());
    &body[..end]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unwraps_cdata_with_markup() {
        let src = r#"<ac:plain-text-body><![CDATA[a < b && c > d
line2]]></ac:plain-text-body>"#;
        let out = preprocess(src);
        assert!(out.contains("a &lt; b &amp;&amp; c &gt; d"), "got: {out}");
        assert!(out.contains('\n'), "newline inside CDATA must survive");
        assert!(!out.contains("<![CDATA["));
    }

    #[test]
    fn rewrites_self_closing_foreign_tags() {
        let src = r#"<ac:link><ri:page ri:content-title="A/B"/><ac:plain-text-link-body><![CDATA[x]]></ac:plain-text-link-body></ac:link>"#;
        let out = preprocess(src);
        assert!(out.contains(r#"<ri:page ri:content-title="A/B"></ri:page>"#), "got: {out}");
    }

    #[test]
    fn leaves_html_void_elements_alone() {
        let src = "<p>a<br/>b</p>";
        assert_eq!(preprocess(src), src);
    }

    #[test]
    fn handles_gt_inside_attribute_quotes() {
        let src = r#"<ri:page ri:content-title="a>b" /><p>x</p>"#;
        let out = preprocess(src);
        assert!(out.contains(r#"<ri:page ri:content-title="a>b"></ri:page>"#), "got: {out}");
    }

    #[test]
    fn unterminated_cdata_becomes_text() {
        let out = preprocess("<ac:plain-text-body><![CDATA[abc");
        assert!(out.contains("abc"));
        assert!(!out.contains("<![CDATA["));
    }
}
