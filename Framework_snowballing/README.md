# Framework Snowballing

## Overview

**Framework Snowballing** is a hybrid web application designed to perform systematic literature reviews using snowballing techniques. It combines a Node.js/Express backend with Python scripts for citation analysis and LLM-based screening.

Access the deployed version of the framework here: https://snowmap.aise-lab.com/

## Key Features

- **Citation Analysis**: Forward and Backward citation tracking using multiple APIs
- **LLM Integration**: Integration with LLM services (Ollama, Gemma, etc.) for automated screening
- **API Aggregation**: Support for multiple citation databases:
  - OpenAlex
  - Semantic Scholar
  - Crossref

- **Web Interface**: User-friendly HTML/CSS frontend for configuration and result visualization

## Repository Structure

```
Framework_snowballing/
├── frontend/             # HTML/CSS user interface
├── controllers/          # Express route handlers
├── routes/               # API route definitions
├── services/             # Session management and backend utilities
├── scripts/              # Python modules for citation analysis and LLM processing
├── package.json          # Node.js dependencies
├── requirements.txt      # Python dependencies
└── README.md
```

## Installation

### Prerequisites
- Node.js 14+ and npm
- Python 3.8+
- Ollama (for LLM analysis, optional)

### Setup

1. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables** (optional):
   ```bash
   export OLLAMA_URL="http://localhost:11434/api/chat"
   export OLLAMA_MODEL="gemma4:31b"
   export PORT="3000"
   ```

## Usage

### Development Mode

Start the development server with auto-reload:
```bash
node app.js
```

The application will be available at `http://localhost:3000`

Enter the DOI Or Title of the seed article and click **Search**.

## License

See `LICENSE` file in the repository root.
