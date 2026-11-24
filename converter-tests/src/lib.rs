#[path = "../../src-tauri/src/converter/mod.rs"]
pub mod converter;
#[path = "../../src-tauri/src/error.rs"]
pub mod error;
#[path = "../../src-tauri/src/models.rs"]
pub mod models;

pub fn golden_convert(s: &str) -> String {
    golden_convert_from(s, "1", "Self")
}

pub fn golden_convert_from(s: &str, id: &str, title: &str) -> String {
    {
        use crate::{converter::*, models::HrefMode};
        let page = PageMeta {
            id: id.into(),
            title: title.into(),
            space_key: "S".into(),
            space_name: "Space".into(),
            web_url: "https://example.invalid/wiki/pages/1".into(),
            ancestors: vec![],
            homepage_id: None,
            version: 1,
            updated: None,
            rel_path: format!("pages/{}.md", title.to_lowercase()),
        };
        let mut index = ExportIndex::default();
        index.base_url = "https://example.invalid".into();
        for (id, title, path) in [
            ("1", "Self", "pages/self.md"),
            ("2", "Other", "pages/other.md"),
        ] {
            index.pages_by_id.insert(
                id.into(),
                IndexedPage {
                    rel_path: path.into(),
                    web_url: format!("https://example.invalid/wiki/pages/{id}"),
                },
            );
            index
                .page_ids_by_title
                .insert(("s".into(), title.into()), id.into());
        }
        index.attachments_by_file_id.insert(
            "a".into(),
            IndexedAttachment {
                rel_path: "assets/diagram.png".into(),
                title: "diagram.png".into(),
                page_id: "1".into(),
            },
        );
        index
            .attachment_ids_by_title
            .insert("diagram.png".into(), "a".into());
        convert_page(
            &page,
            s,
            &index,
            &ConvertOptions {
                page_link: HrefMode::Relative,
                attachment_link: HrefMode::Relative,
                include_document_title: false,
                page_breadcrumbs: false,
                page_properties_as_front_matter: true,
                front_matter_standard: false,
            },
        )
    }
}
