"""
Chaves que ligam/desligam as camadas de persistência do snowballing.

Por enquanto o projeto roda sem banco e sem cache em disco: o PostgreSQL não
está sendo usado e o cache servia resultado velho durante o desenvolvimento.
O código das duas camadas continua aqui, só fica atrás destas chaves — para
religar, basta definir a variável com 1/true/yes/on no .env.

SNOWMAP_DISABLE_CACHE (antiga) continua valendo e vence SNOWMAP_ENABLE_CACHE,
porque test_consistency.py a usa para garantir buscas sem cache.
"""
import os

TRUTHY = {"1", "true", "yes", "on"}


def _flag(name):
    return str(os.getenv(name, "")).strip().lower() in TRUTHY


def cache_enabled():
    if os.getenv("SNOWMAP_DISABLE_CACHE"):
        return False
    return _flag("SNOWMAP_ENABLE_CACHE")


def database_enabled():
    return _flag("SNOWMAP_ENABLE_DB")
