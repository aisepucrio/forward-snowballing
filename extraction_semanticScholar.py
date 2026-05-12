import requests
import pandas as pd

# Paper to analyze
paper_id = "10.1016/j.jss.2021.111044"

# === REAL supported fields from your API test ===
fields = [
    "title",
    "abstract",
    "authors",
    "year",
    "venue",
    "journal",
    "url",
    "isOpenAccess",
    "openAccessPdf",
    "citationCount",
    "referenceCount",
    "isInfluential",
    "publicationTypes",
    "fieldsOfStudy",
    "externalIds",
    "influentialCitationCount"
]

fields_param = ",".join(fields)

# URL definition
url = (
    f"https://api.semanticscholar.org/graph/v1/paper/"
    f"{paper_id}/citations?limit=1000&fields={fields_param}"
)

# Check if it works
res = requests.get(url)
print("HTTP status:", res.status_code)

data = res.json()
print("Response keys:", list(data.keys()))

if "data" in data:
    citations = []

    for c in data["data"]:
        p = c.get("citingPaper", {}) or {}
        record = {}

        # copy all supported fields safely
        for f in fields:
            value = p.get(f, None)

            # convert dict fields (like openAccessPdf, externalIds) to string
            if isinstance(value, dict):
                record[f] = str(value)
            else:
                record[f] = value

        # authors as string
        record["authors_names"] = (
            ", ".join(a.get("name", "") for a in p.get("authors", []))
            if p.get("authors") else None
        )

        # publicationTypes as string
        if isinstance(p.get("publicationTypes"), list):
            record["publicationTypes_str"] = ", ".join(p["publicationTypes"])
        else:
            record["publicationTypes_str"] = None

        # externalIds flatten
        if isinstance(p.get("externalIds"), dict):
            record["externalIds_str"] = ", ".join(
                f"{k}:{v}" for k, v in p["externalIds"].items()
            )
        else:
            record["externalIds_str"] = None

        citations.append(record)

    df = pd.DataFrame(citations)
    df.to_csv("citations_semanticscholar_allfields.csv", index=False)

    print(f"CSV file succefully created with {len(df)} citations and {len(df.columns)} fields.")
else:
    print("absence of field 'data' in the answer:")
    print(data)
