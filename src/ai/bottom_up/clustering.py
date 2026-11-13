"""Unsupervised discovery of groups in wiki page text.

This first prototype uses TF-IDF to represent page text as numerical features,
then K-means to group pages with similar vocabulary. No page categories or
group labels are supplied to the algorithm.
"""

import mwparserfromhell
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer


def _clean_page_text(page_text):
    """Remove wiki markup so the model works with readable page text."""
    return mwparserfromhell.parse(page_text).strip_code().strip()


def discover_page_clusters(pages, number_of_clusters=3, top_term_count=5):
    """Group pages by vocabulary similarity and describe each discovered group.

    Args:
        pages: Iterable of database rows or dictionaries containing page_id,
            title and page_text.
        number_of_clusters: Number of groups K-means should discover.
        top_term_count: Number of representative terms to report per group.

    Returns:
        A dictionary containing the algorithm name and the discovered groups.
    """
    if number_of_clusters < 2:
        raise ValueError("At least two clusters are required.")

    if top_term_count < 1:
        raise ValueError("At least one representative term is required.")

    usable_pages = []
    documents = []

    for page in pages:
        cleaned_text = _clean_page_text(page["page_text"])

        if cleaned_text:
            usable_pages.append(page)
            documents.append(cleaned_text)

    if len(usable_pages) < number_of_clusters:
        raise ValueError(
            "There must be at least as many non-empty pages as requested clusters."
        )

    vectorizer = TfidfVectorizer(
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
    )
    page_vectors = vectorizer.fit_transform(documents)

    if page_vectors.shape[1] == 0:
        raise ValueError("No usable words were found in the supplied pages.")

    model = KMeans(
        n_clusters=number_of_clusters,
        random_state=42,
        n_init=10,
    )
    page_labels = model.fit_predict(page_vectors)
    vocabulary = vectorizer.get_feature_names_out()

    clusters = []

    for cluster_index in range(number_of_clusters):
        member_pages = [
            {
                "page_id": page["page_id"],
                "title": page["title"],
            }
            for page, label in zip(usable_pages, page_labels)
            if label == cluster_index
        ]

        term_weights = model.cluster_centers_[cluster_index]
        top_term_indexes = term_weights.argsort()[::-1][:top_term_count]
        representative_terms = [
            str(vocabulary[index])
            for index in top_term_indexes
            if term_weights[index] > 0
        ]

        clusters.append(
            {
                "cluster_id": cluster_index + 1,
                "page_count": len(member_pages),
                "pages": member_pages,
                "representative_terms": representative_terms,
            }
        )

    return {
        "algorithm": "TF-IDF + K-means",
        "page_count": len(usable_pages),
        "cluster_count": number_of_clusters,
        "clusters": clusters,
    }
