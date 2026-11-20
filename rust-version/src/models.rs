use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Page {
    pub page_id: String,
    pub title: String,
    pub namespace: String,
    pub revision_id: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateFact {
    pub source_page_id: i64,
    pub source_page: String,
    pub subject: String,
    pub relationship: String,
    pub object: String,
    pub evidence: String,
    pub extraction_method: String,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeFact {
    pub subject: String,
    pub relationship: String,
    pub object: String,
    pub source_page: String,
    pub source_page_id: i64,
    pub evidence: String,
    pub extraction_method: String,
    pub confidence: f64,
}
