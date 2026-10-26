import os
from dotenv import load_dotenv


def main() -> int:
    from groq import Groq

    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("GROQ_API_KEY chưa được cấu hình.")
        return 1

    models = Groq(api_key=api_key).models.list()
    print("Danh sách các model khả dụng trên Groq:")
    for model in models.data:
        print(f"- {model.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())