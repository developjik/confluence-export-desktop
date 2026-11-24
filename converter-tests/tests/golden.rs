use converter_contract_tests::golden_convert;

#[test]
fn reviewed_storage_goldens() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("../fixtures/cases.json")).unwrap();
    let cases = cases.as_array().unwrap();
    assert!(cases.len() >= 20, "keep broad storage-format coverage");
    let mut names = std::collections::HashSet::new();
    for case in cases {
        let name = case["name"].as_str().unwrap();
        assert!(names.insert(name), "duplicate fixture: {name}");
        let storage = case["storage"].as_str().unwrap();
        let expected = case["markdown"].as_str().unwrap();
        assert_eq!(golden_convert(storage), expected, "fixture: {name}");
        assert_eq!(
            golden_convert(storage),
            expected,
            "repeat must be deterministic: {name}"
        );
    }
}

#[test]
fn hostile_and_truncated_storage_is_bounded() {
    // No network resolver exists in these converters. Includes are inert, not expanded.
    for input in [
        "<ac:structured-macro",
        "<ac:structured-macro ac:name=\"include\"><ac:parameter>A</ac:parameter>",
        "<ac:link><ri:page ri:content-title=\"B\"/>",
        "<!DOCTYPE x [<!ENTITY x SYSTEM \"file:///does-not-exist\">]><p>&x;</p>",
        "<p>\0</p>",
    ] {
        let first = golden_convert(input);
        assert!(first.len() < 10_000);
        assert_eq!(first, golden_convert(input));
    }
}

#[test]
fn reciprocal_page_links_and_includes_stay_inert() {
    for (id, title, target, filename) in [
        ("1", "Self", "Other", "other.md"),
        ("2", "Other", "Self", "self.md"),
    ] {
        let input = format!(
            "<ac:link><ri:page ri:content-title=\"{target}\" ri:space-key=\"S\"/></ac:link><ac:structured-macro ac:name=\"include\"><ac:parameter>{target}</ac:parameter></ac:structured-macro>"
        );
        assert_eq!(
            converter_contract_tests::golden_convert_from(&input, id, title),
            format!("[{target}]({filename})\n\n<!-- 지원되지 않는 매크로: include -->\n")
        );
    }
}
