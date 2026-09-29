# Snowballing for Review

## Overview

This repository centralizes CSV datasets exported from different snowballing and academic indexing tools, including Google Scholar, OpenAlex, Lens, Semantic Scholar, LitMaps, OpenCitations, ResearchRabbit, and SnowMap. In addition to the datasets, the repository includes analysis notebooks and auxiliary scripts used for constructing citation and reference graphs, comparing tools, and conducting analyses related to the snowballing process in systematic reviews.


### Main Objectives

- Gather and standardize metadata collected from different tools;
- Generate citation and reference graphs to support the exploration of study networks;
- Facilitate comparisons across data sources and promote the reproducibility of the analyses;
- Support the study screening process through the use of LLMs, considering inclusion and exclusion criteria defined by the researchers.

## Repository Structure

```
snowballing_for_review/
├── Data/                  # Datasets exported from the tools
├── Notebooks_Analysis/    # Analysis and graph generation notebooks
├── Quartile/              # Data used for publication venue quartile analysis
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.10+ is recommended.
- All required packages are listed in `requirements.txt`.

To install the dependencies:

```bash
pip install -r requirements.txt
```

## How to Use

### 1. Set Up the Environment
```bash

# Install dependencies
pip install -r requirements.txt

```
### 2. Run the Notebooks

The notebooks available in the `Notebooks_Analysis/` directory reproduce the analyses conducted for each research question presented in the study.

#### RQ1: *What types of article metadata can be extracted using Snowmap in forward and backward snowballing, and how complete and consistent are these data?*

```bash
jupyter notebook rq1_analysis.ipynb
```

Execute the notebook cells sequentially to reproduce the metadata extraction, comparison analyses, and visualizations.

#### RQ2: *Do the studies retrieved by the tools originate from recognized scientific sources in the SE domain?*

```bash
jupyter notebook rq2_analysis.ipynb
```

This notebook reproduces the publication venue and quartile analyses.

#### RQ3: *To what extent do the studies retrieved by each tool align with the ground truth in terms of coverage?*


This notebook reproduces the coverage analyses and graph-based comparisons among the evaluated tools.

The LLM screening evaluation lives in `LLMs_Analysis/`, at the root of the repository, and
is shared with the backward analysis. It runs the screening through the same prompt and
client used by the SnowMap tool and compares the results against the human ground truth.
See the README in that directory.

```bash
python code/run_screening.py study0
python code/compare.py study0
```

---


