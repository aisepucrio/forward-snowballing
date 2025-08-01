# 🧠 Toward Reliable Forward Snowballing in Systematic Literature Reviews: A Comparative Study and Framework Proposal


This repository contains:

- The data used for a comparative study between tools implementing *forward snowballing*;
- An automation tool with a web interface, developed to assist researchers in the process of:
  - Automatic article search via *forward snowballing*;
  - Screening articles based on inclusion and exclusion criteria;
  - Using LLMs to support decision making.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16102191.svg)](https://doi.org/10.5281/zenodo.16102191)

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

**1. `inicial_analisys` (Datasets):**
- Data collected from a seed article, from 5 tools supporting forward snowballing.
- Jupyter Notebook with initial comparative analysis of the data returned by the tools.
- Structure prepared to facilitate data extension and exploration.

**2. `Framework_Snowballing` (Prototype):**
- `controllers/`: application logic.
- `frontend/`: web interface.
- `routes/`: application routes.
- `scripts/`: auxiliary scripts.
- `arquivo.json`: structured data.
- `app.js`: main application file.

---

## ▶️ B. How to Run the Code

1. Download the repository and unzip the files.
2. Install the required libraries (Node.js and Python).
3. Insert your Gemini API key into the file `analisa.js`.

> ⚠️ Note: The user must have a Gemini API key to access the LLM features. However, all other functionalities of the tool can be used without the key.

---

## 📦 C. Requirements

The project was developed and validated on **Linux** environments.  
Users operating on different systems may need to adjust certain commands or dependencies accordingly.

This project uses Node.js and Python. The requirements are organized as follows:

### Node.js & Python
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

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
