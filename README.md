# 🧠 Toward Reliable Forward Snowballing in Systematic Literature Reviews: A Comparative Study and Framework Proposal


This repository brings together two main components:

🔎 1. Comparative study of forward snowballing tools
  - Data and scripts used in a comparative analysis of different tools that implement forward 
    snowballing.
  - The results of this analysis are described in the article referenced in this repository.
  - This analysis served as the basis for the development of the automated tool also included 
    in  this repository.
  - The step-by-step guide for reproducing the analysis is available in the tools_analysis directory.

🛠️ 2. Automated tool with web interface
  - Developed to assist researchers in the following tasks:
    - Automatic article retrieval via forward snowballing;
    - Initial analysis of the retrieved articles;
    - Article screening based on inclusion and exclusion criteria, with support from LLMs.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16755858.svg)](https://doi.org/10.5281/zenodo.16755858)

Access the full paper [here](SBES_IIER_2025___Snowballing.pdf)

## 📚 Citation

If you use this work, please cite the following paper:

```bibtex
@Inproceedings{januario2025:SBES,
  author = {Januário, Jailma and Nicolau, Maria Isabel and Felizardo, Katia Romero and Pereira, Juliana Alves},
  title     = {Toward Reliable Forward Snowballing in Systematic Literature Reviews: A Comparative Study and Framework Proposal},
  year      = {2025},
  pages     = {1–7},
  booktitle = {Brazilian Symposium on Software Engineering, Insightful Ideas and Emerging Results Track (SBES IIER)},  
  publisher = {SOL}
}
```
---


## ✨ Main Features

- 🔍 **Automatic import of articles** via the Semantic Scholar API, using the DOI of a seed article, for example: `10.1016/j.jss.2021.111044`.  
  It is also possible to **export these articles in CSV format**.

- ✅ **Manual screening** of articles, marking them as "**Include**" or "**Exclude**" for subsequent application of inclusion and exclusion criteria.

- 📝 **Insertion of inclusion and exclusion criteria** directly in the interface.

- 📊 **Initial analysis** of articles marked as "Include".

- 🤖 **Automated application** of inclusion and exclusion criteria with support from LLMs (language models).

- 📄 **Export of the final screening results** in CSV format.

---

## 🗂️ A. Repository Organization
**1. `tools_analisys` (Analysis of 5 tools):**
    The structure and description of this directory are provided in its own README file.

**2. `Framework_Snowballing` (Prototype):**
- `controllers/`: application logic.
- `frontend/`: web interface.
- `routes/`: application routes.
- `scripts/`: auxiliary scripts.
- `arquivo.json`: structured data.
- `app.js`: main application file.

---

## ▶️ B. How to Run the Code
The project was developed and validated on **Linux** environments.  
Users operating on different systems may need to adjust certain commands or dependencies accordingly.

1. Download the repository and unzip the files.
2. To use the inclusion and exclusion criteria analysis feature with LLM support, you must add your Gemini API key to the analisa.js file.
  - Navigate to the file:
  ```bash
    cd ./Framework_snowballing/scripts/
  ```
  - Open the analisa.js file and set your API key:
  ```bash
    API_KEY = 'YOUR_API_KEY'
  ```

⚠️ Note: Only the LLM-based screening feature requires a Gemini API key. All other functionalities of the tool can be used without it.

3. Install the required libraries (Node.js and Python).

- Dependencies are listed in the `package.json` file.
- Required libraries are listed in the `requirements.txt` .
```bash
  cd ./Framework_snowballing
  ```
- To install, run:
  ```bash
  cd ./Framework_snowballing
  npm install
  pip install -r requirements.txt
  ```
- In the terminal, run:
   ```bash
   node app.js
  ```
- In your browser, go to: 
  ```bash
  `http://localhost:3000`
  ```
- Enter the DOI of the seed article and click **Search**.
- A tutorial on how to use the tool and the expected outputs on each screen is available [here](<Tool Usage Tutorial.pdf>).

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
