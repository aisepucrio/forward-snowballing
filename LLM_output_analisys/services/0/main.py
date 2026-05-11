from services.generate_articles import gerar_artigos
from services.analisys_LLM import gerar_analise
from services.compare import comparar_jsons

if __name__ == "__main__":
    gerar_artigos("IC_EC.json", "source.csv")
    gerar_analise("articles.json")
    comparar_jsons("resultados_originais.json", "resultados_gemini.json", "comparacao.txt")