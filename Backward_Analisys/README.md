# Backward Snowballing for Review

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
├── LLMs_Analysis/         # Scripts and experiments using LLMs
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

# Clone the repository
git clone <repository-url>
cd snowballing_for_review

# Install dependencies
pip install -r requirements.txt

```
### 2. Run the Notebooks

The notebooks available in the `notebooks_analysis/` directory reproduce the analyses conducted for each research question presented in the study.

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

Instructions for configuring and executing the LLM-related scripts are available in the README file located in the `llms_analysis/` directory.

```bash
python llms_analysis/code/analysis.py
python llms_analysis/code/compare.py
```

---


