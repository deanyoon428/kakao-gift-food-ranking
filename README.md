# Kakao Gift (식품) 랭킹 → GitHub Pages 뷰어 (GitHub-only)

이 레포는 `https://gift.kakao.com/ranking/category/4` (식품 랭킹)을 주기적으로 수집해서
정적 JSON으로 저장하고, GitHub Pages에서 조회하는 **가장 단순한 운영형 MVP 템플릿**입니다.

> ⚠️ 주의: 카카오 페이지 구조/네트워크 API는 변경될 수 있습니다.
> 이 템플릿은 **(1) 네트워크 JSON 응답 자동 탐지 → (2) DOM fallback** 순으로 최대한 견고하게 만들었습니다.
> 첫 실행 후 `docs/data/debug/` 폴더에 저장되는 로그를 보고, 필요하면 파서(heuristics)를 조정하세요.

---

## 1) 동작 개요

- GitHub Actions가 스케줄(기본: 매시간)로 실행
- Playwright로 페이지 접속
- 네트워크(JSON) 응답 중 랭킹 데이터로 보이는 것을 자동 탐지해서 파싱
- `docs/data/food_ranking.json` (최신 스냅샷) 갱신
- `docs/data/food_history.ndjson` (옵션: 히스토리) 한 줄 append
- 변경이 있으면 자동 커밋/푸시
- GitHub Pages가 `docs/`를 배포하고, 화면에서 JSON을 fetch해 렌더링

---

## 2) GitHub Pages 설정

1. GitHub 레포 생성 후 코드 푸시
2. **Settings → Pages**
3. Source: `Deploy from a branch`
4. Branch: `main`
5. Folder: `/docs`

---

## 3) 로컬에서 먼저 테스트 (권장)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r crawler/requirements.txt
python -m playwright install --with-deps chromium
python crawler/crawl_food.py
```

성공하면:
- `docs/data/food_ranking.json` 생성/갱신
- `docs/data/food_history.ndjson` 누적
- 실패하면 `docs/data/debug/`에 스크린샷/HTML/네트워크 캡처가 남습니다.

---

## 4) Actions 스케줄

- `.github/workflows/crawl.yml`에서 cron을 수정하세요.
- cron은 **UTC 기준**입니다. (KST=UTC+9)

---

## 5) 필드 스펙

`docs/data/food_ranking.json`:

```json
{
  "source": "https://gift.kakao.com/ranking/category/4",
  "fetched_at": "2026-03-04T00:00:00Z",
  "items": [
    {
      "rank": 1,
      "title": "상품명",
      "price": "12,900원",
      "product_url": "https://gift.kakao.com/product/....",
      "image_url": "https://... (있으면)",
      "raw": { "원본 일부(옵션)" : "..." }
    }
  ]
}
```

---

## 6) 다음 단계(운영 고도화)

- 변동 감지(Top10 변동 / 1위 변경 / 신규진입) 후 텔레그램 알림
- API 엔드포인트가 확정되면 DOM fallback 제거 → 훨씬 안정적
