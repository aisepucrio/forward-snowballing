import sys
import json
import os
from dotenv import load_dotenv
load_dotenv()

from snowmap_bd import update_result_flags

def main():
    try:
        payload = json.loads(sys.argv[1])

        search_id = payload.get("search_id")
        paper_id = payload.get("paper_id")
        
        selected = payload.get("selected_first_page")
        if selected is not None:
            selected = bool(selected)
            
        excluded = payload.get("excluded_duplicate")
        if excluded is not None:
            excluded = bool(excluded)

        duplicate_of = payload.get("duplicate_of")

        if not search_id or not paper_id:
            print(json.dumps({"error": "search_id e paper_id são obrigatórios"}))
            sys.exit(1)

        update_result_flags(
            search_id=search_id,
            paper_id=paper_id,
            selected_first_page=selected,
            excluded_duplicate=excluded,
            duplicate_of=duplicate_of,
        )

        print(json.dumps({"success": True}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()