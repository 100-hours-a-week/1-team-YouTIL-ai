import evaluate
from bert_score import score as bert_score
from typing import Optional

# import nltk
# nltk.download('punkt')

def compute_scores(reference: str, prediction: str, similarity_score: Optional[float] = None) -> dict:
    # BLEU
    bleu = evaluate.load("bleu")
    bleu_score = bleu.compute(predictions=[prediction], references=[[reference]])["bleu"]

    # ROUGE
    rouge = evaluate.load("rouge")
    rouge_score = rouge.compute(predictions=[prediction], references=[reference])["rougeL"]

    # BERTScore
    P, R, F1 = bert_score([prediction], [reference], lang="ko")
    bert_score_f1 = F1[0].item()
    
    return {
        "bleu_score": bleu_score,
        "rouge_score": rouge_score,
        "bert_score": bert_score_f1,
        "avg_similarity_score": similarity_score
    }