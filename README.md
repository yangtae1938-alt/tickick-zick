# 찍찍 급등 전 레이더 MVP

## 실행 방법
Python 3.10 이상 권장.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Streamlit이 출력하는 로컬 URL을 브라우저에서 엽니다. 휴대폰에서 외부 접속하려면 앱을 배포할 서버가 필요합니다.

## 현재 기능
- 티커 목록을 입력해 일봉 데이터 스캔
- RVOL(일봉 기준), 최근 가격 압축, 20일 고점 접근 등 기초 신호
- 주가/시총/공급자 제공 Float/평균 거래대금 필터
- SEC CIK 매핑, 최근 제출 서류 및 원문 링크
- 등록 서류/자금조달 관련 키워드 위험 플래그
- CSV 내보내기

## 한계
- 기본 티커 목록은 데모용이며 미국 전체 종목 자동 발굴은 아닙니다.
- Yahoo Finance 데이터는 지연·누락·요청 제한이 있을 수 있습니다.
- SEC 키워드 플래그는 원문 계약 해석을 대체하지 않습니다. EFFECT, ATM 가동, 재판매 가능 수량 등을 자동 확정하지 않습니다.
- 자동 반복 스캔/푸시 알림/실시간 분봉/역병합 데이터베이스/백테스트는 아직 포함하지 않았습니다.
- SEC 요청에는 유효한 연락처를 포함한 User-Agent를 사용하세요. `app.py`의 `SEC_UA`를 실제 연락처로 바꾸는 것을 권장합니다.
