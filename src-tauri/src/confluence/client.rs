use std::time::Duration;

use base64::Engine;
use futures::StreamExt;
use serde::de::DeserializeOwned;
use url::Url;

use crate::confluence::types::{
    ApiAttachment, ApiPage, ApiSpace, CurrentUser, Paged, RawAttachment, RawPage, RawSpace, RawUser,
};
use crate::error::{AppError, AppResult};

const PAGE_EXPAND: &str = "body.storage,version,ancestors,space";
const RETRY_STATUS: [u16; 5] = [413, 429, 502, 503, 504];

#[derive(Debug, Clone)]
pub struct ClientConfig {
    pub timeout_seconds: u64,
    pub max_retries: u32,
}

impl Default for ClientConfig {
    fn default() -> Self {
        Self { timeout_seconds: 30, max_retries: 5 }
    }
}

pub struct ConfluenceClient {
    base: String,
    http: reqwest::Client,
    auth_header: String,
    config: ClientConfig,
}

impl ConfluenceClient {
    pub fn new(base_url: &str, email: &str, token: &str, config: ClientConfig) -> AppResult<Self> {
        let base = crate::confluence::urls::normalize_base_url(base_url)?;
        let auth_header = format!(
            "Basic {}",
            base64::engine::general_purpose::STANDARD.encode(format!("{email}:{token}"))
        );
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(config.timeout_seconds.max(5)))
            .connect_timeout(Duration::from_secs(15))
            .build()
            .map_err(|err| AppError::api("HTTP_CLIENT_FAILED", "HTTP 클라이언트를 초기화하지 못했습니다.", format!("{err}")))?;
        Ok(Self { base, http, auth_header, config })
    }

    pub fn base_url(&self) -> &str {
        &self.base
    }

    fn url(&self, path: &str) -> AppResult<Url> {
        let path = path.trim_start_matches('/');
        Url::parse(&format!("{}/{}", self.base, path))
            .map_err(|err| AppError::config("URL_INVALID", "요청 URL을 만들지 못했습니다.", format!("{path}: {err}")))
    }

    async fn send_with_retry(&self, url: Url) -> AppResult<reqwest::Response> {
        let mut attempt: u32 = 0;
        loop {
            let resp = self
                .http
                .get(url.clone())
                .header("Authorization", &self.auth_header)
                .header("Accept", "application/json")
                .send()
                .await
                .map_err(map_network_error)?;
            let status = resp.status();
            if RETRY_STATUS.contains(&status.as_u16()) && attempt < self.config.max_retries {
                let wait = resp
                    .headers()
                    .get("Retry-After")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|v| v.parse::<u64>().ok())
                    .map(Duration::from_secs)
                    .unwrap_or_else(|| backoff_delay(attempt));
                tracing::warn!("{} on {} — retrying in {:?} (attempt {})", status, url, wait, attempt + 1);
                tokio::time::sleep(wait).await;
                attempt += 1;
                continue;
            }
            if status.is_client_error() || status.is_server_error() {
                let body = resp.text().await.unwrap_or_default();
                return Err(AppError::api(
                    "REQUEST_FAILED",
                    format!("Confluence API 요청이 실패했습니다. ({status})"),
                    truncate(&body, 2000),
                ));
            }
            return Ok(resp);
        }
    }

    async fn get_json<T: DeserializeOwned>(&self, path: &str) -> AppResult<T> {
        let url = self.url(path)?;
        let resp = self.send_with_retry(url).await?;
        resp.json::<T>()
            .await
            .map_err(|err| AppError::api("RESPONSE_PARSE_FAILED", "응답을 해석하지 못했습니다.", format!("{err}")))
    }

    async fn get_paged<T: DeserializeOwned>(&self, path: &str, limit: usize) -> AppResult<Vec<T>> {
        let mut out = Vec::new();
        let mut start = 0usize;
        loop {
            let separator = if path.contains('?') { '&' } else { '?' };
            let paged: Paged<T> = self
                .get_json(&format!("{path}{separator}start={start}&limit={limit}"))
                .await?;
            let count = paged.results.len();
            out.extend(paged.results);
            let has_next = paged.links.map(|l| l.next.is_some()).unwrap_or(false);
            if count == 0 || !has_next {
                break;
            }
            start += count.max(1);
        }
        Ok(out)
    }

    // ---------- public API ----------

    pub async fn current_user(&self) -> AppResult<CurrentUser> {
        let user: RawUser = self.get_json("/rest/api/user/current").await?;
        Ok(CurrentUser {
            display_name: user.display_name.unwrap_or_else(|| "사용자".into()),
            email: user.email,
            account_id: user.account_id.unwrap_or_default(),
        })
    }

    pub async fn get_page(&self, page_id: &str) -> AppResult<ApiPage> {
        let raw: RawPage = self
            .get_json(&format!("/rest/api/content/{page_id}?expand={PAGE_EXPAND}"))
            .await?;
        Ok(raw.into_page())
    }

    /// Direct child pages of a page (one level).
    pub async fn child_pages(&self, page_id: &str) -> AppResult<Vec<ApiPage>> {
        let raws: Vec<RawPage> = self
            .get_paged(&format!("/rest/api/content/{page_id}/child/page"), 50)
            .await?;
        // child/page does not apply expansions from the list endpoint; fetch each child fully.
        let mut pages = Vec::with_capacity(raws.len());
        for raw in raws {
            match self.get_page(&raw.id).await {
                Ok(page) => pages.push(page),
                Err(err) => {
                    tracing::warn!("failed to fetch child page {}: {err}", raw.id);
                }
            }
        }
        Ok(pages)
    }

    /// All pages of a space.
    pub async fn space_pages(&self, space_key: &str) -> AppResult<Vec<ApiPage>> {
        let key = urlencoding(space_key);
        let raws: Vec<RawPage> = self
            .get_paged(&format!("/rest/api/space/{key}/content/page?type=page&expand={PAGE_EXPAND}"), 50)
            .await?;
        Ok(raws.into_iter().map(RawPage::into_page).collect())
    }

    /// All spaces visible to the user.
    pub async fn list_spaces(&self) -> AppResult<Vec<ApiSpace>> {
        let raws: Vec<RawSpace> = self.get_paged("/rest/api/space", 50).await?;
        Ok(raws
            .into_iter()
            .map(|s| ApiSpace {
                key: s.key,
                name: s.name,
                homepage_id: s.homepage.map(|h| h.id),
            })
            .collect())
    }

    pub async fn get_space(&self, space_key: &str) -> AppResult<ApiSpace> {
        let key = urlencoding(space_key);
        let raw: RawSpace = self
            .get_json(&format!("/rest/api/space/{key}?expand=homepage"))
            .await?;
        Ok(ApiSpace {
            key: raw.key,
            name: raw.name,
            homepage_id: raw.homepage.map(|h| h.id),
        })
    }

    pub async fn page_attachments(&self, page_id: &str) -> AppResult<Vec<ApiAttachment>> {
        let raws: Vec<RawAttachment> = self
            .get_paged(&format!("/rest/api/content/{page_id}/child/attachment"), 100)
            .await?;
        Ok(raws.into_iter().map(RawAttachment::into_attachment).collect())
    }

    pub async fn download_attachment(&self, download_path: &str) -> AppResult<Vec<u8>> {
        let path = format!("/wiki{}", download_path);
        let url = self.url(&path)?;
        let resp = self.send_with_retry(url).await?;
        let bytes = resp
            .bytes()
            .await
            .map_err(|err| AppError::api("DOWNLOAD_FAILED", "첨부파일을 내려받지 못했습니다.", format!("{err}")))?;
        Ok(bytes.to_vec())
    }

    /// Resolve a page by title within a space using CQL search.
    pub async fn search_page_by_title(
        &self,
        space_key: &str,
        title: &str,
    ) -> AppResult<Option<(String, String)>> {
        let cql = format!(
            "space={} and title=\"{}\"",
            urlencoding(space_key),
            title.replace('\\', "\\\\").replace('"', "\\\"")
        );
        let paged: Paged<RawPage> = self
            .get_json(&format!("/rest/api/content/search?cql={}&limit=1", urlencoding(&cql)))
            .await?;
        Ok(paged
            .results
            .into_iter()
            .next()
            .map(|p| (p.id.clone(), p.links.and_then(|l| l.webui).unwrap_or_default())))
    }

    /// Recursively collect a page and all descendants with bounded concurrency.
    pub async fn collect_with_descendants(
        &self,
        root_id: &str,
        max_concurrency: usize,
        cancel: &crate::error::CancelFlag,
    ) -> AppResult<Vec<ApiPage>> {
        let root = self.get_page(root_id).await?;
        let mut collected: Vec<ApiPage> = vec![root.clone()];
        let mut frontier: Vec<String> = vec![root.id];
        while !frontier.is_empty() {
            if cancel.is_cancelled() {
                return Err(AppError::new("Run", "CANCELLED", "실행이 취소되었습니다.", "", false));
            }
            let results: Vec<AppResult<Vec<ApiPage>>> = futures::stream::iter(frontier.drain(..))
                .map(|id| async move { self.child_pages(&id).await })
                .buffer_unordered(max_concurrency.max(1))
                .collect()
                .await;
            for group in results {
                for page in group? {
                    frontier.push(page.id.clone());
                    collected.push(page);
                }
            }
        }
        Ok(collected)
    }
}

fn map_network_error(err: reqwest::Error) -> AppError {
    if err.is_timeout() {
        AppError::api("TIMEOUT", "요청 시간이 초과되었습니다.", format!("{err}"))
    } else if err.is_connect() {
        AppError::api("CONNECT_FAILED", "Confluence 서버에 연결하지 못했습니다.", format!("{err}"))
    } else {
        AppError::api("NETWORK_ERROR", "네트워크 요청이 실패했습니다.", format!("{err}"))
    }
}

fn backoff_delay(attempt: u32) -> Duration {
    let secs = (2u64).saturating_pow(attempt).min(60);
    Duration::from_secs(secs.max(1))
}

fn urlencoding(value: &str) -> String {
    // Only escape what CQL/URL paths require; Confluence treats + as space in query params.
    const SET: &percent_encoding::AsciiSet = &percent_encoding::NON_ALPHANUMERIC
        .remove(b'-')
        .remove(b'_')
        .remove(b'.')
        .remove(b'~');
    percent_encoding::utf8_percent_encode(value, SET).to_string()
}

fn truncate(text: &str, max: usize) -> String {
    if text.len() <= max {
        text.to_string()
    } else {
        let mut cut = max;
        while cut > 0 && !text.is_char_boundary(cut) {
            cut -= 1;
        }
        format!("{}…", &text[..cut])
    }
}
