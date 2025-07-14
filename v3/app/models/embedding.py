from transformers import AutoTokenizer, AutoModel
from typing import List
import logging
import torch

logger = logging.getLogger(__name__)

class EbeddingModelConfig:
    EMBEDDING_MODEL: str = "BAAI/bge-m3"


class EmbeddingModel:
    def __init__(self, config: EbeddingModelConfig = EbeddingModelConfig()):
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._initialize_embedding()

    def _initialize_embedding(self):
        self.embedding_tokenizer = AutoTokenizer.from_pretrained(self.config.EMBEDDING_MODEL)
        self.embedding_model = AutoModel.from_pretrained(self.config.EMBEDDING_MODEL).to(self.device)
        self.embedding_model.eval()

    async def get_embedding(self, text: str) -> List[float]:
        try:
            inputs = self.embedding_tokenizer(text, return_tensors="pt", truncation=True, max_length=1024)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            outputs = self.embedding_model(**inputs)
            with torch.no_grad():
                outputs = self.embedding_model(**inputs)
                embeddings = outputs.last_hidden_state.mean(dim=1)  # mean pooling
            return embeddings[0].tolist()
        except Exception as e:
            logger.error(f"임베딩 생성 실패: {e}")
            raise

    @property
    def embedding_dimension(self) -> int:
        return self.embedding_model.config.hidden_size