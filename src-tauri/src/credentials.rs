use crate::error::{AppError, AppResult};

pub const SERVICE: &str = "ConfluenceExportDesktop";

/// Same key scheme as v1: `ConfluenceExportDesktop:<base_url>:<email>`.
pub fn credential_key(base_url: &str, email: &str) -> String {
    let normalized = base_url.trim().trim_end_matches('/').to_lowercase();
    format!("{SERVICE}:{normalized}:{}", email.trim().to_lowercase())
}

fn entry(key: &str) -> AppResult<keyring::Entry> {
    keyring::Entry::new(SERVICE, key).map_err(|err| {
        AppError::new(
            "Auth",
            "KEYRING_UNAVAILABLE",
            "OS 자격증명 저장소에 접근하지 못했습니다.",
            format!("{err}"),
            false,
        )
    })
}

pub fn save_token(base_url: &str, email: &str, token: &str) -> AppResult<()> {
    let key = credential_key(base_url, email);
    let entry = entry(&key)?;
    // Update-in-place: set_password handles both create and replace on all backends,
    // but some backends error on update of a missing credential, so delete first.
    let _ = entry.delete_credential();
    entry
        .set_password(token)
        .map_err(|err| AppError::new("Auth", "TOKEN_WRITE_FAILED", "API 토큰을 저장하지 못했습니다.", format!("{err}"), false))
}

pub fn read_token(base_url: &str, email: &str) -> Option<String> {
    let key = credential_key(base_url, email);
    let entry = entry(&key).ok()?;
    match entry.get_password() {
        Ok(token) => Some(token),
        Err(keyring::Error::NoEntry) => None,
        Err(err) => {
            tracing::warn!("keyring read failed for {key}: {err}");
            None
        }
    }
}

pub fn delete_token(base_url: &str, email: &str) -> AppResult<()> {
    let key = credential_key(base_url, email);
    let entry = entry(&key)?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(err) => Err(AppError::new(
            "Auth",
            "TOKEN_DELETE_FAILED",
            "저장된 API 토큰을 삭제하지 못했습니다.",
            format!("{err}"),
            false,
        )),
    }
}

/// Reads a token that v1 stored through CredWriteW with a UTF-16LE blob.
#[cfg(windows)]
pub fn read_v1_native_token(base_url: &str, email: &str) -> Option<String> {
    use windows::core::PCWSTR;
    use windows::Win32::Security::Credentials::{
        CredFree, CredReadW, CREDENTIALW, CRED_TYPE_GENERIC,
    };

    let key: Vec<u16> = credential_key(base_url, email).encode_utf16().chain([0]).collect();
    let mut ptr: *mut CREDENTIALW = std::ptr::null_mut();
    // SAFETY: `key` is a valid NUL-terminated wide string and `ptr` is a valid out-param.
    let result = unsafe { CredReadW(PCWSTR(key.as_ptr()), CRED_TYPE_GENERIC, None, &mut ptr) };
    if result.is_err() {
        return None;
    }
    // SAFETY: `ptr` points at a credential owned by the credential manager until CredFree.
    unsafe {
        let cred = &*ptr;
        let size = cred.CredentialBlobSize as usize;
        let blob = std::slice::from_raw_parts(cred.CredentialBlob, size);
        let words: Vec<u16> = blob
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect();
        let text = String::from_utf16_lossy(&words);
        CredFree(ptr.cast());
        let trimmed = text.trim_matches('\0').to_string();
        if trimmed.is_empty() { None } else { Some(trimmed) }
    }
}

#[cfg(not(windows))]
pub fn read_v1_native_token(_base_url: &str, _email: &str) -> Option<String> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn credential_key_matches_v1_scheme() {
        let key = credential_key("https://Team.Atlassian.net/", "User@Example.com");
        assert_eq!(key, "ConfluenceExportDesktop:https://team.atlassian.net:user@example.com");
    }
}
