# Student A evaluation results (A12)

Generated 2026-11-07 15:09 on Windows AMD64, Python 3.11.9 by `eval/run_eval.py`. Models loaded in 26.0 s.

## Search quality (44 questions, 24 frames, en/fr/ar)

| | Recall@1 | Recall@3 | MRR | right & confident (≥ 0.25) | unanswerable but confident |
|---|---|---|---|---|---|
| **all** | 0.84 | 0.92 | 0.88 | 0.84 | 0.00 |
| ar | 0.60 | 0.80 | 0.69 | 0.60 | 0.00 |
| en | 0.94 | 0.94 | 0.94 | 0.94 | 0.00 |
| fr | 0.91 | 1.00 | 0.95 | 0.91 | 0.00 |

### Which signals matter (ablation)

| Score uses | Recall@1 | MRR | unanswerable but confident |
|---|---|---|---|
| full (0.5 image + 0.3 text + 0.2 OCR) | 0.84 | 0.88 | 0.00 |
| picture only (CLIP image) | 0.78 | 0.82 | 0.14 |
| caption only (CLIP text) | 0.35 | 0.40 | 0.29 |
| OCR words only | 0.32 | 0.32 | 0.00 |
| no OCR (0.6 image + 0.4 text) | 0.78 | 0.82 | 0.00 |

Search latency: 25.5 ms mean, 28.6 ms p95.

Questions whose first result was not a right frame:

- *elevator* (en): right frame at rank –, first was `sortie_fr` (0.33)
- *Où est l'ascenseur ?* (fr): right frame at rank 2, first was `exit_en_dark` (0.36)
- *الطابق الأول* (ar): right frame at rank 3, first was `stairs_up` (0.41)
- *وين المصعد؟* (ar): right frame at rank –, first was `exit_en_dark` (0.38)
- *درج* (ar): right frame at rank 5, first was `two_men` (0.31)
- *غرفة جلوس فيها تلفاز* (ar): right frame at rank 3, first was `exit_en_dark` (0.37)

## OCR on signs (word recall 0.80, CER 0.14)

| Sign | True text | Read | Word recall | CER |
|---|---|---|---|---|
| exit_en | EXIT Room 204 | EXIT Room 204 | 1.00 | 0.00 |
| exit_en_dark | EXIT Room 204 | EXIT Room 204 | 1.00 | 0.00 |
| sortie_fr | Sortie Escalier | Sortie Escalier | 1.00 | 0.00 |
| exit_ar | مخرج الطابق الأول | مخرج الطابق الأول | 1.00 | 0.00 |
| pharmacy | PHARMACIE صيدلية | PHARMACIE 4112 | 0.50 | 0.38 |
| elevator | ASCENSEUR مصعد | ASCENSEUR مصعل | 0.50 | 0.07 |
| toilets | TOILETTES WC | TOILETTES WC | 1.00 | 0.00 |
| room105 | Salle 105 Dr. Haddad | Salle 105 Dr. Haddad | 1.00 | 0.00 |
| cafeteria | Cafeteria 8:00 - 16:00 | Cafeteria 8.00 = 16:00 | 1.00 | 0.00 |
| stop_sign | STOP | d01$ | 0.00 | 1.00 |

## Warnings (CLIP zero-shot)

| Kind | Threshold | TP | FP | FN | TN | Precision | Recall |
|---|---|---|---|---|---|---|---|
| stairs | 0.5 | 4 | 0 | 0 | 20 | 1.00 | 1.00 |
| closed_door | 0.45 | 3 | 0 | 0 | 21 | 1.00 | 1.00 |

## Speed per stored frame (24 frames, laptop CPU)

| Stage | mean ms | p95 ms |
|---|---|---|
| quality | 3.3 | 6 |
| enhance | 7.4 | 12 |
| faces | 42.7 | 73 |
| warnings | 84.0 | 125 |
| ocr | 1728.0 | 3182 |
| objects | 72.1 | 102 |
| embed | 20.3 | 27 |
| store | 20.6 | 28 |
| **total** | **1978.4** | **3477** |

