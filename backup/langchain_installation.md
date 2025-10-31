# LangChain 패키지 설치 가이드

## 필수 패키지 설치

```bash
pip install langchain-core langchain-chroma langchain-google-genai chromadb
```

## 개별 설치 (선택사항)

```bash
pip install langchain-core        # 핵심 Document 클래스
pip install langchain-chroma       # ChromaDB 통합
pip install langchain-google-genai # Google Generative AI 임베딩
pip install chromadb               # Vector Database
```

## 버전 확인

```bash
pip show langchain-core langchain-chroma langchain-google-genai chromadb
```

## 주의사항

- `langchain.schema.Document`는 deprecated되었습니다
- 최신 버전에서는 `langchain_core.documents.Document`를 사용합니다
- LangChain v0.1.0 이후로 모듈 구조가 변경되었습니다

## 문제 해결

만약 여전히 import 오류가 발생하면:

```bash
# 기존 langchain 패키지 제거 (충돌 방지)
pip uninstall langchain -y

# 필수 패키지만 재설치
pip install langchain-core langchain-chroma langchain-google-genai chromadb
```
