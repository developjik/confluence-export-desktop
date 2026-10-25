use serde::Serialize;

/// Uniform application error surfaced to the UI with a stable code.
#[derive(Debug, thiserror::Error)]
#[error("{category}/{code}: {message}")]
pub struct AppError {
    pub category: String,
    pub code: String,
    pub message: String,
    pub detail: String,
    pub retryable: bool,
}

impl AppError {
    pub fn new(category: &str, code: &str, message: impl Into<String>, detail: impl Into<String>, retryable: bool) -> Self {
        Self {
            category: category.to_string(),
            code: code.to_string(),
            message: message.into(),
            detail: detail.into(),
            retryable,
        }
    }

    pub fn config(code: &str, message: impl Into<String>, detail: impl Into<String>) -> Self {
        Self::new("Config", code, message, detail, false)
    }

    pub fn auth(code: &str, message: impl Into<String>, detail: impl Into<String>) -> Self {
        Self::new("Auth", code, message, detail, false)
    }

    pub fn api(code: &str, message: impl Into<String>, detail: impl Into<String>) -> Self {
        Self::new("ConfluenceApi", code, message, detail, true)
    }
}

impl Serialize for AppError {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut s = serializer.serialize_struct("AppError", 5)?;
        s.serialize_field("category", &self.category)?;
        s.serialize_field("code", &self.code)?;
        s.serialize_field("message", &self.message)?;
        s.serialize_field("detail", &self.detail)?;
        s.serialize_field("retryable", &self.retryable)?;
        s.end()
    }
}

impl From<anyhow::Error> for AppError {
    fn from(err: anyhow::Error) -> Self {
        AppError::new("Internal", "INTERNAL_ERROR", "내부 오류가 발생했습니다.", format!("{err:#}"), false)
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Clone, Default)]
pub struct CancelFlag(std::sync::Arc<std::sync::atomic::AtomicBool>);

impl CancelFlag {
    pub fn new() -> Self {
        Self(std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false)))
    }

    pub fn cancel(&self) {
        self.0.store(true, std::sync::atomic::Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(std::sync::atomic::Ordering::SeqCst)
    }

    pub fn handle(&self) -> std::sync::Arc<std::sync::atomic::AtomicBool> {
        self.0.clone()
    }

    pub fn from_handle(handle: std::sync::Arc<std::sync::atomic::AtomicBool>) -> Self {
        Self(handle)
    }
}

impl CancelFlag {
    #[allow(clippy::new_without_default)]
    pub fn fresh() -> Self {
        Self::new()
    }
}
