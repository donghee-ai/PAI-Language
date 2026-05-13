"""Language 파트 데스크톱 UI (Tkinter).

채팅 형식 창 하나로 사용자 입력과 GPT 답변을 보여준다. Vision 의 실시간 장면
요약은 상단 상태줄에만 표시하고, 카메라 프레임 단위 로그/HTTP 로그 등 잡음은
화면 대신 ``logs/ui_session.log`` 파일로 보낸다.

실행 (PAI-Language 루트에서):

    python -m language.ui
"""

from __future__ import annotations

import logging
from pathlib import Path

# --- 로깅: GUI 가 뜨기 전에 root 핸들러를 파일로 잡아둔다 ---------------------
# language.main 은 import 시점에 logging.basicConfig(...) 를 호출하는데, root 에
# 이미 핸들러가 있으면 그 호출은 no-op 이 되므로 콘솔 폭주를 막을 수 있다.
_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "ui_session.log"
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    filename=str(_LOG_PATH),
    filemode="a",
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

import asyncio
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from language.config import Config
from language.main import LanguageApp

log = logging.getLogger(__name__)

# emit 으로 들어온 한 줄을 어떤 스타일로 표시할지 결정하기 위한 접두어들.
_META_PREFIXES = ("[근거]", "[명령", "[Action]", "[오류]", "처리 중")


class LanguageUI:
    """LanguageApp 을 백그라운드 asyncio 루프에서 돌리고 Tk 창으로 입출력한다."""

    def __init__(self) -> None:
        self.config = Config()
        try:
            self.config.validate()
        except RuntimeError as exc:
            messagebox.showerror("설정 오류", str(exc))
            raise SystemExit(1)

        self.loop = asyncio.new_event_loop()
        self._out_q: "queue.Queue[str]" = queue.Queue()
        self.app = LanguageApp(self.config, emit=self._emit_threadsafe)

        self._busy = False  # LLM 호출 진행 중 (중복 전송 방지)
        self._build_widgets()

        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        self._greet()
        self.root.after(50, self._drain_output)
        self.root.after(1000, self._refresh_vision)

    def _greet(self) -> None:
        # GPT(LLM) 가 준비된 상태(API 키 검증 통과)에서 띄우는 인사. WS 연결 같은
        # 내부 상태는 사용자에게 노출하지 않는다.
        self._append(
            "안녕하세요! PAI-Language 입니다. 무엇을 도와드릴까요?\n"
            "카메라에 보이는 물체를 물어보거나(예: \"지금 뭐가 보여?\"), "
            "\"마우스 집어줘\" 같은 명령을 입력해 보세요.",
            "answer",
        )

    # -- asyncio 스레드 ------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.app.hub.run())
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - 백그라운드 스레드, 로그만 남기고 종료
            log.exception("WS 루프가 예외로 종료됨")
        finally:
            self.loop.close()

    def _emit_threadsafe(self, *args: object) -> None:
        # LanguageApp 은 asyncio 스레드에서 emit 을 호출한다. Tk 위젯은 메인
        # 스레드에서만 만질 수 있으므로 큐에만 넣고, 메인 쪽에서 주기적으로 비운다.
        self._out_q.put(" ".join(str(a) for a in args))

    # -- Tk 위젯 -------------------------------------------------------------

    def _build_widgets(self) -> None:
        ui_font = "Malgun Gothic"  # Windows 한글 폰트 — Tk 에는 영문 패밀리명으로 줘야 안정적

        self.root = tk.Tk()
        self.root.title("PAI-Language")
        self.root.geometry("880x780")
        self.root.minsize(600, 520)
        self.root.configure(background="#f0f0f0")

        top = tk.Frame(self.root, background="#f0f0f0")
        top.pack(side="top", fill="x", padx=14, pady=(12, 4))
        self.vision_var = tk.StringVar(value="현재 카메라: (대기 중)")
        tk.Label(top, textvariable=self.vision_var, anchor="w", background="#f0f0f0",
                 fg="#0a7a4f", font=(ui_font, 11, "bold")).pack(fill="x")
        tk.Label(top, text=f"LLM: {self.config.openai_model}", anchor="w",
                 background="#f0f0f0", fg="#999999", font=(ui_font, 9)).pack(fill="x")

        # 입력줄(bottom)을 먼저 bottom 쪽에 고정한 뒤 채팅창이 남는 공간을 채우게 한다.
        # 이렇게 해야 창이 작아져도 입력칸이 잘리지 않는다.
        bottom = tk.Frame(self.root, background="#f0f0f0")
        bottom.pack(side="bottom", fill="x", padx=14, pady=(0, 14))

        self.chat = scrolledtext.ScrolledText(
            self.root, wrap="word", state="disabled", font=(ui_font, 12), height=14,
            background="#ffffff", relief="solid", borderwidth=1, padx=12, pady=10,
            spacing1=2, spacing3=4,
        )
        self.chat.pack(side="top", fill="both", expand=True, padx=14, pady=8)
        self.chat.tag_config("user", foreground="#1565c0", font=(ui_font, 12, "bold"),
                             spacing1=8)
        self.chat.tag_config("answer", foreground="#1a1a1a")
        self.chat.tag_config("meta", foreground="#9a9a9a")

        self.entry = tk.Entry(bottom, font=(ui_font, 13), relief="solid", borderwidth=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._on_submit())
        self.entry.focus_set()
        self.send_btn = tk.Button(
            bottom, text="보내기", font=(ui_font, 12), command=self._on_submit,
            padx=18, pady=8, cursor="hand2",
        )
        self.send_btn.pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _append(self, text: str, tag: str = "answer") -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text + "\n", tag)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    # -- 이벤트 핸들러 -------------------------------------------------------

    def _on_submit(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        if text.lower() in ("quit", "exit", "q"):
            self._on_close()
            return
        if self._busy:
            return  # 이전 요청 처리 중 — 무시
        self.entry.delete(0, "end")
        self._append(f"나> {text}", "user")
        self._set_busy(True)
        fut = asyncio.run_coroutine_threadsafe(self.app.handle_user_input(text), self.loop)
        fut.add_done_callback(self._on_request_done)

    def _on_request_done(self, fut: "asyncio.Future") -> None:
        exc = fut.exception()
        if exc is not None:
            self._out_q.put(f"[오류] 처리 실패: {exc}")
        # busy 해제는 메인 스레드에서
        self.root.after(0, lambda: self._set_busy(False))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_btn.configure(state="disabled" if busy else "normal")

    def _drain_output(self) -> None:
        try:
            while True:
                line = self._out_q.get_nowait()
                tag = "meta" if line.startswith(_META_PREFIXES) else "answer"
                self._append(line, tag)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_output)

    def _refresh_vision(self) -> None:
        try:
            ctx = self.app.vision.to_context_string()
        except Exception:  # noqa: BLE001
            ctx = "현재 카메라: (오류)"
        self.vision_var.set(ctx or "현재 카메라: (대기 중)")
        self.root.after(1000, self._refresh_vision)

    def _on_close(self) -> None:
        def _cancel_all() -> None:
            for task in asyncio.all_tasks(self.loop):
                task.cancel()

        try:
            self.loop.call_soon_threadsafe(_cancel_all)
        except Exception:  # noqa: BLE001
            pass
        # asyncio 스레드(daemon)가 정리할 시간을 잠깐 준 뒤 창 종료
        self.root.after(150, self.root.destroy)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    LanguageUI().run()


if __name__ == "__main__":
    main()
