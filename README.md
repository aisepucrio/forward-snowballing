# SnowMap: A Tool to Support the Snowballing Process in Literature Reviews

SnowMap is a tool designed to support the snowballing process in secondary studies by assisting researchers in performing both backward and forward snowballing. This repository contains the SnowMap framework, the datasets collected from different academic sources, and the scripts used to reproduce the analyses reported in the associated publication.

The repository aims to promote transparency, reproducibility, and reuse of the experimental artifacts generated during the evaluation of SnowMap and its comparison with other tools available in the literature.

## Publication

The full paper describing SnowMap and the conducted experiments is available in this repository:

* [SnowMap: A Tool to Support the Snowballing Process in Literature Reviews](28231_Paper_.pdf)

## Evaluated Tools

The experiments and analyses included in this repository were conducted using data collected from the following academic indexing and snowballing tools:

* Google Scholar
* OpenAlex
* Lens
* Semantic Scholar
* OpenCitations
* Litmaps
* ResearchRabbit
* SnowMap

These tools were evaluated and compared regarding metadata extraction, coverage, graph generation capabilities, and support for the snowballing process.

## Repository Structure

The repository is organized into three main directories:

```text
.
├── Backward_Analysis/
├── Forward_Analysis/
├── Framework_snowballing/
├── LICENSE
└── README.md
```

### Backward_Analysis

Contains datasets, scripts, notebooks, and experimental artifacts related to the evaluation of **backward snowballing**. This directory includes analyses performed using data collected from multiple academic indexing and snowballing tools.

Detailed instructions for reproducing the experiments are available in:

```text
Backward_Analysis/README.md
```

### Forward_Analysis

Contains datasets, scripts, notebooks, and experimental artifacts related to the evaluation of **forward snowballing**. The analyses in this directory focus on the studies retrieved through forward citation tracking and their comparison across different tools.

Detailed instructions for reproducing the experiments are available in:

```text
Forward_Analysis/README.md
```

### Framework_snowballing

Contains the source code and scripts that implement the SnowMap framework.

Detailed instructions for reproducing the experiments are available in:

```text
Framework_snowballing/README.md
```

## Getting Started

Clone the repository:

```bash
git clone https://github.com/aisepucrio/forward-snowballing/tree/main
cd forward-snowballing
```

Navigate to the directory of interest and follow the instructions provided in its corresponding `README.md` file.

## Reproducibility

This repository provides the datasets, scripts, and notebooks required to reproduce the analyses presented in the paper.

The experimental workflow is divided according to the snowballing strategy being evaluated:

* **Backward snowballing experiments:** `Backward_Analysis/`
* **Forward snowballing experiments:** `Forward_Analysis/`
* **Framework implementation:** `Framework_snowballing/`

Each directory contains detailed documentation describing the required dependencies, execution steps, and expected outputs.

## Requirements

The dependencies required for each experiment are documented within the corresponding subdirectories.

When available, install the required packages using:

```bash
pip install -r requirements.txt
```

## Data Availability

All datasets and experimental artifacts used in the study are provided within the repository unless otherwise stated in the corresponding documentation.

The repository includes data collected from multiple academic indexing and snowballing tools, supporting the reproducibility of the analyses presented in the publication.



## License

This project is licensed under the terms described in the `LICENSE` file.
