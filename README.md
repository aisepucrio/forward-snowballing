# 🧠 Toward Reliable Forward Snowballing in Systematic Literature Reviews: A Comparative Study and Framework Proposal

This repository contains:

- The data used for a comparative study between tools implementing *forward snowballing*;
- An automation tool with a web interface, developed to assist researchers in the process of:
  - Automatic article search via *forward snowballing*;
  - Screening articles based on inclusion and exclusion criteria;
  - Using LLMs to support decision making.

The paper's PDF is available in this repository.

## 📚 Citation

If you use this work, please cite the following paper:

```bibtex
@inproceedings{Januário2025Toward,
  title={Toward Reliable Forward Snowballing in Systematic Literature Reviews: A Comparative Study and Framework Proposal},
  author={Januário. Jailma, Nicolau. Maria Isabel S. B., Felizardo. Katia, Pereira. Juliana Alves},
  booktitle={SBES-Simpósio Brasileiro de Engenharia de Software, Recife, PE },
  year={2025},
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
4. In your browser, go to: : `http://localhost:3000`
5. Enter the DOI of the seed article and click **Search**.

> ⚠️ Note: The user must have a Gemini API key to use the LLM functionality.

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

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
