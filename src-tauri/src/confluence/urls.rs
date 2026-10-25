use crate::error::{AppError, AppResult};
use url::Url;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Target {
    Page { id: String, space_key: Option<String> },
    Space { key: String },
    Org,
}

/// Normalize a Confluence cloud base URL: scheme + host only.
pub fn normalize_base_url(base_url: &str) -> AppResult<String> {
    let raw = base_url.trim();
    let with_scheme = if raw.starts_with("http://") || raw.starts_with("https://") {
        raw.to_string()
    } else {
        format!("https://{raw}")
    };
    let parsed = Url::parse(&with_scheme).map_err(|_| {
        AppError::config("INVALID_BASE_URL", "Confluence Base URL 형식을 확인하세요.", raw)
    })?;
    Ok(format!(
        "{}://{}",
        parsed.scheme().to_lowercase(),
        parsed.host_str().unwrap_or_default().to_lowercase()
    ))
}

/// Extract the path segments of a wiki URL relative to the base URL.
fn relative_segments(base_url: &str, target: &str) -> Vec<String> {
    let base = normalize_base_url(base_url).unwrap_or_default();
    let parsed = match Url::parse(target.trim()) {
        Ok(url) => url,
        Err(_) => return Vec::new(),
    };
    let target_origin = format!("{}://{}", parsed.scheme().to_lowercase(), parsed.host_str().unwrap_or_default().to_lowercase());
    let mut path = parsed.path().trim().to_string();
    if target_origin == base {
        // same origin: strip nothing; wiki paths start with /wiki
    } else if !base.is_empty() && (path.starts_with(&format!("{base}/")) || target.trim().starts_with(&format!("{base}/"))) {
        // target embeds the base URL as a prefix
        path = target.trim().to_string();
        let idx = path.find(&base).map(|i| i + base.len()).unwrap_or(0);
        path = path[idx..].to_string();
    }
    path.split('/')
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect()
}

/// Parse a page/space/org URL into a concrete export target.
pub fn parse_target(base_url: &str, target_url: &str) -> AppResult<Target> {
    let target_url = target_url.trim();
    if target_url.is_empty() {
        return Err(AppError::config("URL_REQUIRED", "Confluence URL을 입력하세요.", ""));
    }
    let page_id_from_query = Url::parse(target_url)
        .ok()
        .and_then(|url| {
            url.query_pairs()
                .find(|(key, _)| key == "pageId")
                .map(|(_, value)| value.to_string())
        });

    let segments = relative_segments(base_url, target_url);
    // strip a leading "wiki" segment (both /wiki/spaces/K/... and /wiki/K/...)
    let segs: Vec<String> = if segments.first().map(String::as_str) == Some("wiki") {
        segments[1..].to_vec()
    } else {
        segments
    };

    // /spaces/{key}/pages/{id}... and /{key}/pages/{id}...
    if let Some(pages_idx) = segs.iter().position(|s| s == "pages") {
        if pages_idx > 0 && segs.len() > pages_idx + 1 {
            let id = segs[pages_idx + 1]
                .chars()
                .take_while(|c| c.is_ascii_digit())
                .collect::<String>();
            if !id.is_empty() {
                let space_key = if segs[pages_idx - 1] == "spaces" && pages_idx >= 2 {
                    Some(segs[pages_idx - 2].clone())
                } else {
                    Some(segs[pages_idx - 1].clone())
                };
                return Ok(Target::Page { id, space_key });
            }
        }
    }
    if let Some(id) = page_id_from_query {
        let digits: String = id.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !digits.is_empty() {
            return Ok(Target::Page { id: digits, space_key: None });
        }
    }
    // /spaces/{key}... or /{key}
    if !segs.is_empty() {
        let key = if segs[0] == "spaces" {
            if segs.len() < 2 {
                return Err(AppError::config("URL_INVALID", "URL에서 스페이스를 찾을 수 없습니다.", target_url));
            }
            segs[1].clone()
        } else {
            segs[0].clone()
        };
        let looks_like_space = !key.contains('.') && key.len() <= 255;
        if looks_like_space {
            return Ok(Target::Space { key });
        }
    }
    // fall back to org if the URL is just the base (possibly with /wiki)
    Ok(Target::Org)
}

#[cfg(test)]
mod tests {
    use super::*;

    const BASE: &str = "https://team.atlassian.net";

    #[test]
    fn parses_classic_page_url() {
        let t = parse_target(BASE, "https://team.atlassian.net/wiki/spaces/PROD/pages/123456/Page+Title").unwrap();
        assert_eq!(t, Target::Page { id: "123456".into(), space_key: Some("PROD".into()) });
    }

    #[test]
    fn parses_new_page_url() {
        let t = parse_target(BASE, "https://team.atlassian.net/wiki/PROD/pages/123456/Page").unwrap();
        assert_eq!(t, Target::Page { id: "123456".into(), space_key: Some("PROD".into()) });
    }

    #[test]
    fn parses_page_id_query() {
        let t = parse_target(BASE, "https://team.atlassian.net/wiki/pages/viewpage.action?pageId=987654").unwrap();
        assert_eq!(t, Target::Page { id: "987654".into(), space_key: None });
    }

    #[test]
    fn parses_space_url() {
        let t = parse_target(BASE, "https://team.atlassian.net/wiki/spaces/PROD").unwrap();
        assert_eq!(t, Target::Space { key: "PROD".into() });
        let t2 = parse_target(BASE, "https://team.atlassian.net/wiki/PROD/overview").unwrap();
        assert_eq!(t2, Target::Space { key: "PROD".into() });
    }

    #[test]
    fn parses_org() {
        assert_eq!(parse_target(BASE, BASE).unwrap(), Target::Org);
        assert_eq!(parse_target(BASE, "https://team.atlassian.net/wiki").unwrap(), Target::Org);
    }

    #[test]
    fn normalizes_base() {
        assert_eq!(normalize_base_url("https://Team.Atlassian.net/").unwrap(), "https://team.atlassian.net");
        assert_eq!(normalize_base_url("team.atlassian.net").unwrap(), "https://team.atlassian.net");
    }
}
