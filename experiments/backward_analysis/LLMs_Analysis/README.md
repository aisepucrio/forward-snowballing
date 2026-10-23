# LLMs Analysis

This directory contains scripts and experiments related to the use of LLMs for scientific study screening, including comparisons between LLM-generated classifications and manually produced ground truth data.

## Structure

- `code/`
  - `analysis.py` — executes the LLM-based screening process.
  - `compare.py` — compares the LLM results with the ground truth and generates evaluation metrics.
  - `prompt.py` — builds prompts using inclusion/exclusion criteria and article metadata.
- `prompts.txt` — prompts generated during the experiments.
- `study0/` and `study1/` — directories containing datasets and generated results for each study.

## Workflow

1. `prompt.py` loads the article data and the inclusion/exclusion criteria to generate the prompts sent to the LLM.
2. `analysis.py` sends the prompts to the Gemini API and generates binary classification results:
   - `1` = include the study
   - `0` = exclude the study
3. `compare.py` compares the LLM predictions with the ground truth and computes evaluation metrics.

## Running the Scripts

Create a `.env` file in the root directory of `llms_analysis` containing your Gemini API key:

```text
GEMINI_API_KEY=your_api_key_here
```

Run the analysis script:

```bash
python code/analysis.py
```

Run the comparison script:

```bash
python code/compare.py
```

## Requirements

- Python 3.10+ is recommended.
- A valid Gemini API key is required to execute `analysis.py`.