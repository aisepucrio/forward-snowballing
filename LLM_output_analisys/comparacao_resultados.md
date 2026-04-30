# Resultados

## Prompt original

Total de artigos avaliados: 110
True Positives (TP): 7
False Positives (FP): 11
True Negatives (TN): 86
False Negatives (FN): 6

Recall: 0.5384
Acuracia: 0.8454
Precision: 0.3888
F1-score: 0.4510


## Prompt v2

Artigos ignorados por resultado 'not conclusive': 6
Total de artigos avaliados: 104
True Positives (TP): 6
False Positives (FP): 5
True Negatives (TN): 88
False Negatives (FN): 5

Recall: 0.5455
Acuracia: 0.9038
F1-score: 0.5455

## Prompt v2 corrigindo not conclusives

Artigos ignorados por decisao nao contabilizavel: 7
Total de artigos avaliados: 103
True Positives (TP): 6
False Positives (FP): 5
True Negatives (TN): 87
False Negatives (FN): 5

Recall: 0.5455
Precision: 0.5455
Acuracia: 0.9029
F1-score: 0.5455

Distribuicao por criterio (JSON da LLM):
Distribuicao por criterio:
LLM > IC1: Yes 92.86% | No 0.00% | Not conclusive 7.14%
Source > IC1: Yes 99.09% | No 0.91% | Not conclusive 0.00%
LLM > IC2: Yes 84.69% | No 15.31% | Not conclusive 0.00%
Source > IC2: Yes 63.64% | No 36.36% | Not conclusive 0.00%
LLM > IC3: Yes 19.39% | No 79.59% | Not conclusive 1.02%
Source > IC3: Yes 24.55% | No 75.45% | Not conclusive 0.00%
LLM > EC1: Yes 10.20% | No 82.65% | Not conclusive 7.14%
Source > EC1: Yes 2.73% | No 97.27% | Not conclusive 0.00%
LLM > EC2: Yes 8.16% | No 39.80% | Not conclusive 52.04%
Source > EC2: Yes 9.09% | No 90.91% | Not conclusive 0.00%
LLM > EC3: Yes 1.02% | No 96.94% | Not conclusive 2.04%
Source > EC3: Yes 5.45% | No 94.55% | Not conclusive 0.00%
LLM > EC4: Yes 32.65% | No 65.31% | Not conclusive 2.04%
Source > EC4: Yes 18.18% | No 81.82% | Not conclusive 0.00%


## Prompt v2 corrigido not conclusives IC/EC refeitos


IC/EC
IC1: The abstract is written in English.
IC2:The paper explicitly addresses configurable software systems, defined as systems with variability through configuration options (e.g., features, parameters, or modules), and this aspect is central to the paper (e.g., in its objectives, methods, or evaluation).
IC3: The paper deals with techniques to statistically learn data from a sample of configurations, as opposed to considering e.g. the single use of optimization techniques to search for the best (set of) configuration(s), and the use of sampling techniques for SPL testing purposes.
EC1: Papers are excluded if the title and/or abstract indicate that the main contribution is in artificial intelligence or machine learning without explicit reference to configurable software systems or variability (e.g., no mention of configuration options, features).
EC2: Papers are excluded if the title and/or abstract clearly identify the study as a secondary study (e.g., literature review, systematic review, survey, mapping study), position paper, editorial, or experience report without a technical method or empirical evaluation.

Artigos ignorados por decisao nao contabilizavel: 0
Total de artigos avaliados: 109
True Positives (TP): 6
False Positives (FP): 8
True Negatives (TN): 88
False Negatives (FN): 7

Recall: 0.4615
Precision: 0.4286
Acuracia: 0.8624
F1-score: 0.4444

Distribuicao por criterio:
LLM > IC1:    Yes 99.08% | No 00.92% | Not conclusive 00.00%
Source > IC1: Yes 99.08% | No 00.92% | Not conclusive 00.00%
LLM > IC2:    Yes 85.32% | No 14.68% | Not conclusive 00.00%
Source > IC2: Yes 63.30% | No 36.70% | Not conclusive 00.00%
LLM > IC3:    Yes 12.84% | No 87.16% | Not conclusive 00.00%
Source > IC3: Yes 23.85% | No 76.15% | Not conclusive 00.00%
LLM > EC1:    Yes 03.67% | No 96.33% | Not conclusive 00.00%
Source > EC1: Yes 01.83% | No 98.17% | Not conclusive 00.00%
LLM > EC2:    Yes 45.87% | No 54.13% | Not conclusive 00.00%
Source > EC2: Yes 09.17% | No 90.83% | Not conclusive 00.00%
LLM > EC3:    Yes 00.00% | No 00.00% | Not conclusive 00.00%
Source > EC3: Yes 05.50% | No 94.50% | Not conclusive 00.00%
LLM > EC4:    Yes 00.00% | No 00.00% | Not conclusive 00.00%
Source > EC4: Yes 18.35% | No 81.65% | Not conclusive 00.00%

\\ToDo corrigir correspondências