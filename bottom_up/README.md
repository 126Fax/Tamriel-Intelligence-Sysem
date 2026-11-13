# Bottom-up AI – Lore Discovery System

## 1. Application Overview

The Bottom-up AI application will use machine learning techniques to analyse information from the Elder Scrolls universe using data extracted from the UESP Wiki.

Unlike the top-down application, this system will learn patterns from data rather than relying entirely on manually programmed rules.

## 2. Problem Being Addressed

The UESP Wiki contains a large amount of information about characters, locations, events and other aspects of the Elder Scrolls universe.

Identifying similarities and patterns across this information manually can be time-consuming.

This application aims to explore how machine learning can help discover and organise information within a large knowledge base.

## 3. Intended Users

- Elder Scrolls fans interested in exploring lore.
- Researchers interested in fictional world-building.
- Users looking to discover similarities between lore entries.

## 4. Proposed AI Techniques

The application will use a bottom-up AI approach, where behaviour is developed through learning from data.

Potential techniques include:

- Machine learning.
- Clustering.
- Classification.
- Natural language processing.
- Similarity analysis.

The final techniques will be selected during development based on the available data and project requirements.

## 5. Proposed Features

- Analyse information extracted from the UESP Wiki.
- Identify similarities between lore entries.
- Group related information using machine learning.
- Explore patterns within character and location descriptions.
- Present the results in an understandable format.

## 6. Data Source

The application will use information extracted from the UESP Wiki XML dump.

The data will need to be cleaned, processed and converted into a suitable format for machine learning.

## 7. Development and Testing

The application will be developed using Python.

Potential libraries include:

- pandas for data processing.
- scikit-learn for machine learning.
- NumPy for numerical operations.

Testing will cover:

- Data quality.
- Model performance.
- Prediction or clustering results.
- Unseen data.
- Limitations and reliability.

## 8. Future Improvements

Potential improvements include:

- Comparing different machine learning algorithms.
- Analysing additional categories of lore.
- Improving the quality of extracted information.
- Exploring neural networks.
- Developing visual representations of discovered patterns.


## First working prototype: page clustering

The first experiment uses unsupervised machine learning to group main-namespace wiki pages by similarities in their text.

It uses two steps:

1. **TF-IDF** converts each page into numerical word features. Words that are common across every page carry less weight than words that help distinguish one page from another.
2. **K-means** groups pages with similar feature vectors. The algorithm is not given the correct groups in advance.

The prototype reports the pages in each group and the words that most strongly represent that group. These are clues about possible patterns, not verified lore facts.

### Run it

Install the project dependencies:

```bash
pip install -r requirements.txt
```

After importing the synthetic fixture or a UESP dump into the database:

```bash
python -m src.ai.bottom_up.run_clustering --clusters 3
```

Use `--clusters 2` to ask the algorithm to form two groups instead.

The first tests use the synthetic fixture to verify that the algorithm runs and accounts for every eligible page. Meaningful conclusions about Elder Scrolls lore must be evaluated later against a larger real dataset.
