# Language ↔ Coordinator 명령 스키마 (초안 v0.2)

> **상태**: 초안 — Action팀 / Coordinator팀 리뷰 및 합의 필요
> **작성일**: 2026-05-07 (v0.1) / 2026-05-09 갱신 (v0.2)
> **작성**: Language 파트
> **현 단계 (Phase 1, 2026-05-08~)**: Coordinator 미구현 → Language는 PAI-Vision 서버에
> 직결합되어 `vision_update`만 수신한다. 본 문서의 `robot_command` / `action_status`
> 메시지는 **wire로 전송되지 않으며**, 사용자 입력 → LLM 파싱 결과는 stdout으로만 출력된다.
> Phase 2 (Coordinator 도입) 시 `COORDINATOR_ENABLED=1` 설정으로 활성화된다.

---

## 1. 개요

Language 파트가 OpenAI API를 통해 파싱한 명령을 Coordinator(중앙 WebSocket/ROS2 브로커)로 전달하는 메시지 형식을 정의한다.  
모든 WebSocket 메시지는 **공통 Envelope**으로 감싸며, `data` 필드에 타입별 페이로드를 담는다.

---

## 2. 공통 WS 메시지 Envelope

```json
{
  "type": "string",
  "timestamp": "ISO 8601 string",
  "sender": "string",
  "data": { }
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | Y | 메시지 종류 식별자 (아래 타입 목록 참조) |
| `timestamp` | string | Y | 메시지 생성 시각 (UTC, ISO 8601) |
| `sender` | string | Y | 발신 파트: `"language"` \| `"vision"` \| `"action"` |
| `data` | object | Y | 타입별 페이로드 |

### 메시지 타입 목록

| `type` 값 | 방향 | 설명 |
|-----------|------|------|
| `vision_update` | Vision → Coordinator | YOLO 프레임 결과 |
| `vision_update` | Coordinator → Language | relay |
| `robot_command` | Language → Coordinator | 파싱된 로봇 명령 |
| `robot_command` | Coordinator → Action | relay |
| `action_status` | Action → Coordinator | 실행 상태 |
| `action_status` | Coordinator → Language | relay |

---

## 3. robot_command 스키마

Language가 Coordinator로 전송하는 핵심 메시지.

### Envelope 예시

```json
{
  "type": "robot_command",
  "timestamp": "2026-05-07T06:02:53.202093+00:00",
  "sender": "language",
  "data": {
    "action": "pick_and_place",
    "target": "ball",
    "destination": "basket",
    "reasoning": "사용자가 공을 바구니에 담으라고 요청함",
    "raw_input": "공 잡아서 바구니에 넣어줘",
    "vision_confirmed": true
  }
}
```

### data 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `action` | string | Y | 수행할 동작 (아래 action 값 목록 참조) |
| `target` | string | Y | 조작 대상 객체의 YOLO label. 대상 없으면 `"none"` |
| `destination` | string | Y | 목적지 객체의 YOLO label. 해당 없으면 `"none"` |
| `reasoning` | string | Y | LLM이 판단한 근거 (한 문장, 디버깅용) |
| `raw_input` | string | Y | 사용자 원본 자연어 입력 |
| `vision_confirmed` | boolean | Y | 명령 생성 시점에 Vision에서 target이 감지된 상태였는지 여부 |

### action 값 목록

| 값 | 설명 | target 필요 | destination 필요 |
|----|------|:-----------:|:----------------:|
| `pick` | 대상 집기 | Y | N |
| `place` | 대상을 목적지에 놓기 | Y | Y |
| `pick_and_place` | 집기 + 놓기 복합 동작 | Y | Y |
| `home` | 홈 자세 복귀 | N | N |
| `stop` | 즉시 정지 | N | N |

### 유효성 규칙

```
1. action이 "pick" 이면 target ≠ "none"
2. action이 "place" 이면 target ≠ "none" AND destination ≠ "none"
3. action이 "pick_and_place" 이면 target ≠ "none" AND destination ≠ "none"
4. action이 "home" 또는 "stop" 이면 target = "none", destination = "none"
5. 모호하거나 안전하지 않은 명령은 action = "stop" 으로 fallback
```

---

## 4. action_status 스키마

Action이 발행하고 Coordinator가 Language로 relay하는 실행 상태 피드백.

### Envelope 예시

```json
{
  "type": "action_status",
  "timestamp": "2026-05-07T06:02:55.100000+00:00",
  "sender": "action",
  "data": {
    "status": "completed",
    "action_ref": "pick_and_place",
    "message": "공을 바구니에 성공적으로 담았습니다"
  }
}
```

### data 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | Y | 실행 상태 (아래 status 값 참조) |
| `action_ref` | string | Y | 이 상태가 참조하는 action 값 |
| `message` | string | N | 상태 설명 (선택, 사용자 출력용) |

### status 값 목록

| 값 | 설명 |
|----|------|
| `received` | 명령 수신 확인 |
| `executing` | 로봇 동작 실행 중 |
| `completed` | 동작 완료 |
| `failed` | 동작 실패 (message에 이유 포함) |

---

## 5. vision_update 스키마 (참고용)

Vision 파트가 발행하고 Coordinator가 Language로 relay하는 메시지.  
Language는 이 메시지에서 `objects` 배열의 최소 필드만 추출하여 OpenAI context에 사용.

### 전체 구조 (Vision 팀 원본)

```json
{
  "type": "vision_update",
  "timestamp": "...",
  "sender": "vision",
  "data": {
    "frame_id": 1711,
    "timestamp": "2026-05-07T06:02:53.202093+00:00",
    "camera_id": "front_rgb",
    "model": "yolo11s-seg.pt",
    "image_size": [1280, 720],
    "inference_ms": 72.68,
    "loop_fps": 8.79,
    "objects": [
      {
        "id": "obj_01",
        "track_id": "track_159",
        "label": "ball",
        "confidence": 0.91,
        "bbox_xyxy": [445.08, 53.99, 904.77, 323.17],
        "center_pixel": [674, 188],
        "area_pixels": 22551,
        "status": "tracked"
      }
    ]
  }
}
```

### Language가 실제로 사용하는 필드

```
objects[].label          → 어떤 객체가 보이는지
objects[].center_pixel   → 대략적 위치 (화면 기준)
objects[].confidence     → 감지 신뢰도
objects[].status         → tracked 여부
```

---

## 6. 사용 시나리오 예시

### 시나리오 1 — 공 잡아서 바구니에 담기

```
User: "빨간 공 잡아서 바구니에 담아줘"

Vision 상태: ball(감지됨), basket(감지됨)

→ robot_command:
{
  "action": "pick_and_place",
  "target": "ball",
  "destination": "basket",
  "reasoning": "공을 바구니에 담는 복합 동작 요청",
  "raw_input": "빨간 공 잡아서 바구니에 담아줘",
  "vision_confirmed": true
}
```

### 시나리오 2 — 대상 미감지 상태에서 명령

```
User: "공 잡아줘"

Vision 상태: ball 미감지

→ robot_command:
{
  "action": "pick",
  "target": "ball",
  "destination": "none",
  "reasoning": "공 집기 요청, 단 현재 vision에서 미감지",
  "raw_input": "공 잡아줘",
  "vision_confirmed": false
}
```

### 시나리오 3 — 홈 복귀

```
User: "원래 자리로 돌아가"

→ robot_command:
{
  "action": "home",
  "target": "none",
  "destination": "none",
  "reasoning": "홈 자세 복귀 요청",
  "raw_input": "원래 자리로 돌아가",
  "vision_confirmed": false
}
```

### 시나리오 4 — 안전 거부 / 모호한 명령

```
User: "아무거나 해봐"

→ robot_command:
{
  "action": "stop",
  "target": "none",
  "destination": "none",
  "reasoning": "명령이 모호하여 안전 정지",
  "raw_input": "아무거나 해봐",
  "vision_confirmed": false
}
```

---

## 7. 합의 필요 사항 (Action / Coordinator 팀 확인 요청)

| 항목 | 현재 초안 | 확인 필요 내용 |
|------|-----------|----------------|
| `target` / `destination` 값 | YOLO label 문자열 그대로 | Action 팀이 label 기반 객체 탐색 가능한지 |
| `pick_and_place` 지원 여부 | 복합 동작으로 제안 | Action에서 단일 명령으로 처리 가능한지, 아니면 `pick` + `place` 분리 전송해야 하는지 |
| `vision_confirmed=false` 처리 | Language가 그대로 전송 | Action이 자체적으로 Vision 재탐색할지, 아니면 Language에서 차단할지 |
| Coordinator WS URL / 포트 | 미정 | Coordinator 스펙 확정 시 `shared/constants.py`에 반영 (Phase 2에서 Coordinator 레포로 이전 예정) |
| Envelope wire 표준 | PAI-Vision이 이미 표준 envelope 송출 | Coordinator가 그대로 통과시킬지, 추가 메타데이터를 부착할지 |
| `shared/` 이전 시점 | Phase 1 동안은 PAI-Language에 임시 거주 | Coordinator 레포가 생기는 시점에 일괄 이전 |

---

## 8. 변경 이력

| 버전 | 날짜       | 내용                                                       |
| ---- | ---------- | ---------------------------------------------------------- |
| v0.1 | 2026-05-07 | 초안 작성                                                  |
| v0.2 | 2026-05-09 | Action Hub 안 폐기, PAI-Coordinator 중앙 허브 구조로 갱신  |
