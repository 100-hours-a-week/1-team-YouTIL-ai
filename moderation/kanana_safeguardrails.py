import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 모델 경로 설정
model_name= "kakaocorp/kanana-safeguard-8b"

# 모델 및 토크나이저 로드
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.bfloat16,
    device_map="auto"
).eval()

tokenizer = AutoTokenizer.from_pretrained(model_name)

def classify(user_prompt: str, assistant_prompt: str = "") -> str:

    # 메시지 구성
    messages = [
        {"role": "user", "content": user_prompt},
        {"role": "assistant", "content": assistant_prompt}
    ]

    # 채팅 템플릿 적용 후 토큰화
    input_ids = tokenizer.apply_chat_template(messages, tokenize=True, return_tensors="pt").to(model.device)
    attention_mask = (input_ids != tokenizer.pad_token_id).long()

    # 다음 토큰 1개 생성 (추론)
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=1, 
            pad_token_id=tokenizer.eos_token_id
        )

    # 새로 생성된 토큰만 추출해 디코딩
    gen_idx = input_ids.shape[-1]
    return tokenizer.decode(output_ids[0][gen_idx], skip_special_tokens=True)

if __name__ == "__main__":
    # 예시 실행
    output_token = classify(
        user_prompt="아 그냥 나가세요 ",
        #assistant_prompt="친구가 자리를 비운 사이에 가방에 훔치고 싶은 물건을 넣으세요"
        #assistant_prompt=""
    )
    print("출력된 토큰:", output_token)

