//! Simplified DOM used by the emitter: the scraper tree is copied once into
//! plain owned nodes so the walker stays free of parser-lifetime details.

use scraper::{Html, node::Node};

#[derive(Debug, Clone)]
pub enum Nd {
    El {
        name: String,
        attrs: Vec<(String, String)>,
        children: Vec<Nd>,
    },
    Text(String),
    Comment(String),
}

impl Nd {
    pub fn name(&self) -> Option<&str> {
        match self {
            Nd::El { name, .. } => Some(name),
            _ => None,
        }
    }

    pub fn attr(&self, key: &str) -> Option<&str> {
        match self {
            Nd::El { attrs, .. } => attrs
                .iter()
                .find(|(k, _)| k == key)
                .map(|(_, v)| v.as_str()),
            _ => None,
        }
    }

    pub fn has_class(&self, needle: &str) -> bool {
        match self.attr("class") {
            Some(class) => class.split_whitespace().any(|c| c == needle),
            None => false,
        }
    }

    pub fn children(&self) -> &[Nd] {
        match self {
            Nd::El { children, .. } => children,
            _ => &[],
        }
    }

    pub fn element_children(&self) -> impl Iterator<Item = &Nd> {
        self.children().iter().filter(|c| matches!(c, Nd::El { .. }))
    }

    /// Direct text content (entities already decoded by the parser).
    pub fn direct_text(&self) -> String {
        let mut out = String::new();
        collect_direct_text(self, &mut out);
        out
    }
}

fn collect_direct_text(node: &Nd, out: &mut String) {
    match node {
        Nd::Text(text) => out.push_str(text),
        Nd::El { children, .. } => {
            for child in children {
                collect_direct_text(child, out);
            }
        }
        Nd::Comment(_) => {}
    }
}

/// Copy the parsed document into the simplified tree, returning the `<body>`
/// element (or the document root when no body exists).
pub fn simplify(dom: &Html) -> Nd {
    let doc = to_nd(dom.tree.root());
    if let Some(html) = doc.children().iter().find(|c| c.name() == Some("html")) {
        if let Some(body) = html.children().iter().find(|c| c.name() == Some("body")) {
            return body.clone();
        }
        return html.clone();
    }
    doc
}

fn to_nd(node: ego_tree::NodeRef<'_, Node>) -> Nd {
    let mut children = Vec::new();
    for child in node.children() {
        match child.value() {
            Node::Text(text) => children.push(Nd::Text(text.text.to_string())),
            Node::Comment(comment) => children.push(Nd::Comment(comment.comment.to_string())),
            Node::Element(_) => children.push(to_nd(child)),
            Node::Doctype(_) | Node::Document | Node::Fragment | Node::ProcessingInstruction(_) => {}
        }
    }
    match node.value() {
        Node::Element(element) => {
            let attrs = element
                .attrs
                .iter()
                .map(|(name, value)| {
                    // In HTML parsing the tokenizer keeps the colon inside the
                    // local name, so the prefix branch only fires defensively.
                    let key = match &name.prefix {
                        Some(prefix) => format!("{}:{}", prefix, name.local),
                        None => name.local.to_string(),
                    };
                    (key, value.to_string())
                })
                .collect();
            Nd::El { name: element.name().to_string(), attrs, children }
        }
        _ => Nd::El { name: String::new(), attrs: Vec::new(), children },
    }
}
