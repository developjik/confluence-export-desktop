use serde::Deserialize;

#[derive(Debug, Clone)]
pub struct CurrentUser {
    pub display_name: String,
    pub email: Option<String>,
    pub account_id: String,
}

#[derive(Debug, Clone)]
pub struct AncestorRef {
    pub id: String,
    pub title: String,
}

#[derive(Debug, Clone)]
pub struct SpaceRef {
    pub key: String,
    pub name: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ApiPage {
    pub id: String,
    pub title: String,
    pub space: SpaceRef,
    pub version: i64,
    pub ancestors: Vec<AncestorRef>,
    pub storage: String,
    /// Relative web UI path such as `/spaces/K/pages/123/Title`.
    pub webui: String,
}

impl ApiPage {
    pub fn web_url(&self, base_url: &str) -> String {
        format!("{}/wiki{}", base_url.trim_end_matches('/'), self.webui)
    }
}

#[derive(Debug, Clone)]
pub struct ApiSpace {
    pub key: String,
    pub name: Option<String>,
    pub homepage_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ApiAttachment {
    pub id: String,
    pub title: String,
    pub version: i64,
    pub file_id: Option<String>,
    pub media_type: Option<String>,
    pub file_size: Option<u64>,
    /// Relative download path from `_links.download`.
    pub download_path: String,
}

impl ApiAttachment {
    /// Extension with a leading dot, derived from the title; empty when absent.
    pub fn extension(&self) -> String {
        match self.title.rsplit_once('.') {
            Some((stem, ext)) if !stem.is_empty() && !ext.is_empty() && ext.len() <= 10 => {
                format!(".{ext}")
            }
            _ => String::new(),
        }
    }
}

// ---------- raw wire structs ----------

#[derive(Debug, Deserialize)]
pub(crate) struct RawPage {
    pub id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub space: Option<RawSpace>,
    #[serde(default)]
    pub version: Option<RawVersion>,
    #[serde(default)]
    pub ancestors: Vec<RawAncestor>,
    #[serde(default)]
    pub body: Option<RawBody>,
    #[serde(default, rename = "_links")]
    pub links: Option<RawLinks>,
}

impl RawPage {
    pub(crate) fn into_page(self) -> ApiPage {
        ApiPage {
            id: self.id,
            title: self.title,
            space: self.space.map(|s| SpaceRef { key: s.key, name: s.name }).unwrap_or(SpaceRef {
                key: String::new(),
                name: None,
            }),
            version: self.version.map(|v| v.number).unwrap_or(0),
            ancestors: self
                .ancestors
                .into_iter()
                .map(|a| AncestorRef { id: a.id, title: a.title })
                .collect(),
            storage: self
                .body
                .and_then(|b| b.storage.map(|s| s.value))
                .unwrap_or_default(),
            webui: self.links.and_then(|l| l.webui).unwrap_or_default(),
        }
    }
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawSpace {
    pub key: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default, rename = "homepage")]
    pub homepage: Option<RawAncestor>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawVersion {
    #[serde(default)]
    pub number: i64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawAncestor {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub title: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawBody {
    #[serde(default)]
    pub storage: Option<RawStorage>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawStorage {
    #[serde(default)]
    pub value: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawLinks {
    #[serde(default)]
    pub webui: Option<String>,
    #[serde(default)]
    pub download: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawUser {
    #[serde(default, rename = "displayName")]
    pub display_name: Option<String>,
    #[serde(default)]
    pub email: Option<String>,
    #[serde(default, rename = "accountId")]
    pub account_id: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawAttachment {
    pub id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub version: Option<RawVersion>,
    #[serde(default)]
    pub extensions: Option<RawAttachmentExtensions>,
    #[serde(default, rename = "_links")]
    pub links: Option<RawLinks>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawAttachmentExtensions {
    #[serde(default, rename = "fileId")]
    pub file_id: Option<String>,
    #[serde(default, rename = "mediaType")]
    pub media_type: Option<String>,
    #[serde(default, rename = "fileSize")]
    pub file_size: Option<String>,
}

impl RawAttachment {
    pub(crate) fn into_attachment(self) -> ApiAttachment {
        ApiAttachment {
            id: self.id,
            title: self.title,
            version: self.version.map(|v| v.number).unwrap_or(0),
            file_id: self.extensions.as_ref().and_then(|e| e.file_id.clone()),
            media_type: self.extensions.as_ref().and_then(|e| e.media_type.clone()),
            file_size: self
                .extensions
                .as_ref()
                .and_then(|e| e.file_size.as_deref())
                .and_then(|s| s.parse::<u64>().ok()),
            download_path: self.links.and_then(|l| l.download).unwrap_or_default(),
        }
    }
}

#[derive(Debug, Deserialize)]
pub(crate) struct Paged<T> {
    pub results: Vec<T>,
    #[serde(default)]
    pub links: Option<RawPagedLinks>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawPagedLinks {
    #[serde(default)]
    pub next: Option<String>,
}
