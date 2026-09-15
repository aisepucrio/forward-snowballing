# LLMs Analysis

This directory contains scripts and experiments related to the use of LLMs for scientific study screening, including comparisons between LLM-generated classifications and manually produced ground truth data.

## Structure

- `code/`
  - `analysis.py` — executes the LLM-based screening process.
  - `compare.py` — compares the LLM results with the ground truth and generates evaluation metrics.
- `prompts.txt` — prompts generated during the experiments.
- `study0/` and `study1/` — directories containing datasets and generated results for each study.

The prompt is **not** defined here. `analysis.py` imports it from
`Framework_snowballing/scripts/services/prompt.py`, the same module used by the SnowMap tool, so
the studies evaluate exactly the prompt that runs in the application.

## Workflow

1. `services/prompt.py` builds the messages for one article with all inclusion/exclusion criteria
   and all available metadata (abstract limited to 2000 characters).
2. `analysis.py` sends one request per article to the Gemini API. The LLM answers `Yes` or `No` for
   each criterion, and the article is selected when every inclusion criterion is `Yes` and no
   exclusion criterion is `Yes`. Each result stores:
   - `selected`: `1` = include the study, `0` = exclude the study
   - `results`: the per-criterion answers
3. `compare.py` compares the LLM predictions with the ground truth and computes evaluation metrics.

## Running the Scripts

Create a `.env` file in the root directory of `LLMs_Analysis` containing your Gemini API key:

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
- The repository must keep the `Framework_snowballing/` folder, which provides the shared prompt module.
