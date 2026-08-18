from services.snowballing_pipeline import OpenAlexReferenceProvider, run_cli


def get_references_openalex(doi):
    return OpenAlexReferenceProvider().get_references(doi)


if __name__ == "__main__":
    run_cli("backward")
