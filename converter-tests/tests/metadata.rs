use converter_contract_tests::{
    converter::*,
    models::{ExportOptions, HrefMode},
};

#[test]
fn full_document_metadata_and_breadcrumbs() {
    let page = PageMeta {
        id: "1".into(),
        title: "A#B\nC".into(),
        space_key: "S".into(),
        space_name: "Space".into(),
        web_url: "https://example.invalid/wiki/1".into(),
        ancestors: vec![
            AncestorLink {
                id: "0".into(),
                title: "Home".into(),
            },
            AncestorLink {
                id: "2".into(),
                title: "Parent".into(),
            },
        ],
        homepage_id: Some("0".into()),
        version: 3,
        updated: Some("2026-01-02".into()),
        rel_path: "pages/a.md".into(),
    };
    let index = ExportIndex {
        base_url: "https://example.invalid".into(),
        ..Default::default()
    };
    let options = ConvertOptions::from_export_options(&ExportOptions {
        include_document_title: true,
        ..Default::default()
    });
    let md = convert_page(&page, "<p>Body</p>", &index, &options);
    assert!(md.starts_with("---\ntitle: \"A#B\nC\"\n"));
    assert!(md.contains("version: 3\nupdated: 2026-01-02"));
    assert!(md.contains("[Parent](https://example.invalid/wiki/spaces/S/pages/2)"));
    assert!(!md.contains("[Home]"));
    assert!(md.contains("# A\\#B C\n\nBody\n"));
    assert_eq!(
        file_href(HrefMode::Absolute, "a b/c.md", "p.md", "wiki"),
        "/a%20b/c.md"
    );
    assert_eq!(file_href(HrefMode::Wiki, "a.md", "p.md", "wiki"), "wiki");
}
