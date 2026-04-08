from generate_articles import gerar_artigos
from analisys_LLM import gerar_analise
from compare import comparar_resultados

if __name__ == "__main__":
    gerar_artigos("IC_EC.json", "source.csv")
    gerar_analise("articles.json")
    #comparar_resultados("source.csv", "resultados.json")cd