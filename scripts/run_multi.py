"""
Snowballing com várias seeds. Lê do stdin {"seeds": [{"type": "doi"|"title", "value": "..."}]}
e imprime o resultado combinado no stdout (ver services/multi_seed.py).
"""
import json
import sys
import traceback

from services.multi_seed import MultiSeedSnowballing


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = MultiSeedSnowballing().run(payload.get("seeds"))
        print(json.dumps(result, ensure_ascii=False))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado na busca com várias seeds."}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
