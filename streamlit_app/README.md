# Harbour Street Cafe AI Copilot — Streamlit Demo

## 실행 방법

```bash
pip install -r requirements.txt --break-system-packages
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml을 열어서 실제 Snowflake 계정 정보와 Anthropic API 키를 입력
streamlit run app.py
```

## 화면 구성

1. **구매 영수증** — 영수증 사진 업로드 → Vision API로 품목/벤더/가격 자동 추출 →
   표에서 확인/수정 → `RAW.PURCHASE_LEDGER`에 저장
2. **판매 리포트** — 일일 cash-up 리포트 사진 업로드 → 품목별 판매량/매출 자동 추출
3. **AI에게 질문하기** — 예시 질문 버튼 클릭 또는 직접 타이핑 → Cortex Agent가 답변,
   실행된 SQL도 펼쳐서 확인 가능
4. **대시보드** — 이번 달 매출/할인손실/구매지출 요약, salmon 구매vs판매 트렌드,
   품목별 매출 순위

## Snowflake 연결 없이도 확인 가능 (데모 모드)

사이드바에 Snowflake 계정 정보를 입력하지 않으면, 각 기능이 **샘플 데이터로 동작**합니다.
UI 흐름만 먼저 확인하고 싶을 때 유용합니다.

## 실제 연결 전 확인해야 할 것

1. **`ask_cortex_agent()` 함수의 REST API 엔드포인트/인증 방식**은 Snowflake 계정
   설정(PAT, OAuth, Key-pair 등)에 따라 조정이 필요할 수 있습니다. 공식 문서:
   https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
2. `current_role`(HSC_OWNER_ROLE / NON_OWNER_ROLE)로 실제 Snowflake 사용자 계정에
   Role이 부여되어 있어야 합니다.
3. `insert_rows()`로 저장할 때 판매 리포트 쪽은 `item_name → item_id` 매핑 로직을
   추가로 넣어야 합니다 (현재는 저장 버튼에 안내 메시지만 표시됨, TODO로 표시해둠).

## 라이브 데모 시 팁

- 예시 질문 버튼을 순서대로 눌러가며 "재고 → 판매 인사이트 → 세무 준비" 흐름으로
  시연하면 스토리텔링이 자연스럽습니다.
- 영수증 업로드는 미리 인쇄해서 사진 찍어둔 실제 이미지로 시연하세요 (mock invoice를
  화면 캡처한 것보다 훨씬 설득력 있습니다).
- 대시보드 탭에서 "Snowflake에 연결하면 실제 데이터로 자동 갱신됩니다" 문구가 보이면
  연결이 안 된 상태이니, 발표 전 반드시 연결 테스트를 먼저 하세요.
