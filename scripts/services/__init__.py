"""
Carrega o .env do projeto assim que qualquer modulo de services e importado.

Precisa acontecer aqui, e nao no ponto de uso: o cache e a busca leem variaveis
de ambiente antes de qualquer chamada ao banco, que ate entao era o unico lugar
que chamava load_dotenv(). Sem isso, nada definido no .env chegava a elas.

Falha silenciosa por design: se python-dotenv nao estiver instalado, o sistema
segue lendo apenas variaveis do ambiente real.
"""
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass
