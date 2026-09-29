import sys
import json

from dotenv import load_dotenv
load_dotenv()

from services.snowmap_bd import update_result_flags_batch


def normalize_update(raw):
    search_id = raw.get("search_id")
    paper_id = raw.get("paper_id")

    selected = raw.get("selected_first_page")
    if selected is not None:
        selected = bool(selected)

    excluded = raw.get("excluded_duplicate")
    if excluded is not None:
        excluded = bool(excluded)

    duplicate_of = raw.get("duplicate_of")

    return {
        "search_id": search_id,
        "paper_id": paper_id,
        "selected_first_page": selected,
        "excluded_duplicate": excluded,
        "duplicate_of": duplicate_of,
    }


def main():
    try:
        raw_updates = json.loads(sys.argv[1])

        if not isinstance(raw_updates, list) or len(raw_updates) == 0:
            print(json.dumps({"error": "updates deve ser uma lista não vazia"}))
            sys.exit(1)

        updates = [normalize_update(item) for item in raw_updates]

        updated_count, skipped = update_result_flags_batch(updates)

        print(json.dumps({
            "success": True,
            "updated": updated_count,
            "skipped": skipped,
        }))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
