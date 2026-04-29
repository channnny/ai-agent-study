# 🟥 1주차 — 킥오프 & 개념 정립

## 🎯 이번 주 목표

팀 전원이 "AI 에이전트가 무엇이고 어디까지 할 수 있는가"에 대한 공통 언어를 확보합니다.

개발자는 Claude Code를 로컬에 설치하고, 파일 읽기/쓰기 에이전트 튜토리얼을 1개 완수합니다.

---

## ✅ 개발자 완료 기준

| 항목 | 완료 기준 |
| --- | --- |
| Claude Code 설치 | `claude` 명령어 실행 가능 |
| 로그인 확인 | `/login` 후 Claude Code 세션 진입 가능 |
| 파일 읽기 실습 | `input/sample-admission-raw.md`를 Claude Code가 읽음 |
| 파일 쓰기 실습 | `output/sample-admission-summary.md` 생성 |
| 구조화 출력 실습 | `output/sample-admission-summary.json` 생성 |
| 로그 작성 | `logs/claude-session-note.md` 작성 |
| 팀 공유 | 체크리스트와 데모 스크립트 공유 |

---

## 🚀 실행 순서

### 1. Claude Code 설치

macOS, Linux, WSL 기준:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Homebrew 사용 시:

```bash
brew install --cask claude-code
```

설치 확인:

```bash
claude --version
```

Claude Code 실행:

```bash
claude
```

최초 실행 시 로그인:

```text
/login
```

---

### 2. 프로젝트 루트로 이동

```bash
cd ai-agent-study/week01
```

---

### 3. Claude Code에 실습 프롬프트 입력

`prompts/claude-code-prompt.md` 파일의 내용을 Claude Code 세션에 붙여넣습니다.

---

### 4. 결과 확인

아래 파일이 생성되거나 업데이트되면 성공입니다.

```text
output/sample-admission-summary.md
output/sample-admission-summary.json
logs/claude-session-note.md
```

---

## 🧪 실습 목표

이번 실습은 "단순히 LLM에게 답변을 받는 것"이 아니라, Claude Code가 다음 작업을 수행하도록 만드는 것입니다.

1. 프로젝트 지시사항 `CLAUDE.md` 읽기
2. 입력 파일 `input/sample-admission-raw.md` 읽기
3. 사람이 검수하기 쉬운 줄글 Markdown 생성
4. DB 입력으로 이어질 수 있는 JSON 생성
5. 실습 로그 작성

---

## 🧭 이번 주에 관찰할 것

- Claude Code가 원본에 없는 내용을 추측하는가?
- 애매한 값이 있을 때 `확인 필요`로 잘 분리하는가?
- Markdown 결과와 JSON 결과가 서로 일치하는가?
- 사람이 검수해야 할 포인트가 명확히 드러나는가?
- 다음 주 업무 프로세스 분석에 필요한 질문이 생겼는가?

---

## 📦 1주차 산출물

- Claude Code 설치 확인 기록
- 파일 읽기/쓰기 실습 결과
- 용어집 v1
- 개발자 체크리스트
- 금요일 데모 스크립트
