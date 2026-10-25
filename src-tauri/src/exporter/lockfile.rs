//! Export lockfile (schema v2): tracks page/attachment versions and paths so
//! unchanged content can be skipped and stale files cleaned up.

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::{AppError, AppResult};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Lockfile {
    #[serde(default)]
    pub schema_version: u32,
    #[serde(default)]
    pub pages: HashMap<String, LockPage>,
}

impl Lockfile {
    pub const SCHEMA_VERSION: u32 = 2;

    pub fn load(target_dir: &Path) -> Lockfile {
        let path = target_dir.join("confluence-export.lock.json");
        let Ok(text) = std::fs::read_to_string(path) else {
            return Lockfile::default();
        };
        match serde_json::from_str::<Lockfile>(&text) {
            Ok(lock) => {
                // v1 CME lockfiles (different shape) are ignored entirely.
                if lock.schema_version == 0 && !lock.pages.is_empty() {
                    Lockfile::default()
                } else {
                    lock
                }
            }
            Err(_) => Lockfile::default(),
        }
    }

    pub fn save(&self, target_dir: &Path) -> AppResult<()> {
        let path = target_dir.join("confluence-export.lock.json");
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|err| {
                AppError::new("Storage", "LOCKFILE_WRITE_FAILED", "lockfile을 저장하지 못했습니다.", format!("{err}"), false)
            })?;
        }
        let body = serde_json::to_string_pretty(self).unwrap();
        std::fs::write(&path, body).map_err(|err| {
            AppError::new("Storage", "LOCKFILE_WRITE_FAILED", "lockfile을 저장하지 못했습니다.", format!("{}: {err}", path.display()), false)
        })?;
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LockPage {
    pub version: i64,
    pub path: String,
    #[serde(default)]
    pub hash: String,
    #[serde(default)]
    pub attachments: HashMap<String, LockAttachment>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LockAttachment {
    pub version: i64,
    pub path: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_through_temp_dir() {
        let dir = std::env::temp_dir().join(format!("ced-lock-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let mut lock = Lockfile { schema_version: 2, pages: HashMap::new() };
        lock.pages.insert(
            "1".into(),
            LockPage {
                version: 3,
                path: "Space/Page.md".into(),
                hash: "abc".into(),
                attachments: HashMap::from([("f1".into(), LockAttachment { version: 2, path: "Space/attachments/f1.png".into() })]),
            },
        );
        lock.save(&dir).unwrap();
        let back = Lockfile::load(&dir);
        assert_eq!(back.schema_version, 2);
        assert_eq!(back.pages["1"].version, 3);
        assert_eq!(back.pages["1"].attachments["f1"].path, "Space/attachments/f1.png");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn missing_file_returns_default() {
        let lock = Lockfile::load(Path::new("/nonexistent/definitely-missing"));
        assert!(lock.pages.is_empty());
        assert_eq!(lock.schema_version, 0);
    }
}
