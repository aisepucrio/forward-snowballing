import sys
import json

from dotenv import load_dotenv
load_dotenv()

from services.snowmap_bd import save_criteria_and_logs


def main():
    try:
        payload = json.loads(sys.stdin.read())

        search_id = payload.get("search_id")
        criteria = payload.get("criteria") or {}
        results = payload.get("results") or []

        if not search_id:
            print(json.dumps({"error": "search_id é obrigatório"}))
            sys.exit(1)

        summary = save_criteria_and_logs(search_id, criteria, results)

        print(json.dumps({"success": True, **summary}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
