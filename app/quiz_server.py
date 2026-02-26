"""ローカル HTTP サーバーモジュール（クイズ回答受付用）。

127.0.0.1 のランダムポートで HTTP サーバーをデーモンスレッドで起動し、
POST /quiz/submit でクイズ回答を受け付けて quiz_scorer で採点する。
"""

from __future__ import annotations

import json
import logging
import threading

from app.i18n import t
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.copilot_client import CopilotClientWrapper
    from app.state_manager import StateManager

logger = logging.getLogger(__name__)


class _QuizRequestHandler(BaseHTTPRequestHandler):
    """クイズ回答を受け付ける HTTP リクエストハンドラ。"""

    # score_func はサーバー生成時に注入される
    score_func: Callable[..., Any] | None = None
    copilot_client: CopilotClientWrapper | None = None
    state_manager: StateManager | None = None
    app_config: AppConfig | None = None

    def log_message(self, format: str, *args: Any) -> None:
        """ログ出力を Python logging に統合する。"""
        logger.debug("QuizServer: %s", format % args)

    def do_OPTIONS(self) -> None:  # noqa: N802
        """CORS プリフライトリクエストに対応する。"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        """POST リクエストを処理する。"""
        if self.path == "/quiz/submit":
            self._handle_quiz_submit()
        else:
            self.send_error(404, "Not Found")

    def _set_cors_headers(self) -> None:
        """CORS ヘッダーを設定する。"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _handle_quiz_submit(self) -> None:
        """クイズ回答を受け付けて採点する。"""
        try:
            # リクエストボディの読み込み
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json_response(400, {"error": t("server.error_empty_body")})
                return

            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            topic_key = data.get("topic_key", "")
            q1_choice = data.get("q1_choice", "")
            q2_answer = data.get("q2_answer", "")
            briefing_file = data.get("briefing_file", "")

            if not topic_key:
                self._send_json_response(400, {"error": t("server.error_topic_key_required")})
                return

            logger.info("クイズ回答受信: %s (Q1=%s)", topic_key, q1_choice)

            # 採点実行
            if self.score_func is None:
                self._send_json_response(500, {"error": t("server.error_scorer_not_init")})
                return

            result = self.score_func(
                topic_key=topic_key,
                q1_choice=q1_choice,
                q2_answer=q2_answer,
                briefing_file=briefing_file,
                copilot_client=self.copilot_client,
                state_manager=self.state_manager,
                app_config=self.app_config,
            )

            # 結果をレスポンスとして返す
            response_data = {
                "topic_key": result.topic_key,
                "q1_correct": result.q1_correct,
                "q1_correct_answer": result.q1_correct_answer,
                "q1_explanation": result.q1_explanation,
                "q2_evaluation": result.q2_evaluation,
                "q2_feedback": result.q2_feedback,
                "new_level": result.new_level,
                "next_quiz_at": result.next_quiz_at,
                "level_change": result.level_change,
            }

            self._send_json_response(200, response_data)
            logger.info("採点結果返却: %s — Q1=%s, Q2=%s", topic_key, result.q1_correct, result.q2_evaluation)

        except json.JSONDecodeError:
            self._send_json_response(400, {"error": t("server.error_json_parse")})
        except Exception as e:
            logger.exception("採点中にエラーが発生しました")
            self._send_json_response(500, {
                "error": t("server.error_scoring_failed", error=e),
                "message": t("server.error_retry_later"),
            })

    def _send_json_response(self, status: int, data: dict[str, Any]) -> None:
        """JSON レスポンスを送信する。"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.end_headers()
        response = json.dumps(data, ensure_ascii=False)
        self.wfile.write(response.encode("utf-8"))


class QuizServer:
    """ローカル HTTP サーバーのライフサイクルを管理するクラス。"""

    def __init__(self) -> None:
        """QuizServer を初期化する。"""
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    @property
    def port(self) -> int:
        """サーバーのポート番号を返す。"""
        return self._port

    @property
    def is_running(self) -> bool:
        """サーバーが実行中かどうかを返す。"""
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(
        self,
        *,
        score_func: Callable[..., Any],
        copilot_client: CopilotClientWrapper,
        state_manager: StateManager,
        app_config: AppConfig,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> int:
        """HTTP サーバーをデーモンスレッドで起動する。

        Args:
            score_func: 採点関数（quiz_scorer.score）。
            copilot_client: Copilot クライアントラッパー。
            state_manager: 状態マネージャ。
            app_config: アプリケーション設定。
            host: バインドホスト（デフォルト: 127.0.0.1）。
            port: バインドポート（0 でランダム割当）。

        Returns:
            割り当てられたポート番号。
        """
        if self.is_running:
            logger.warning("QuizServer は既に起動しています (port=%d)", self._port)
            return self._port

        # ハンドラにスコアリング関数を注入
        handler = type(
            "_BoundQuizHandler",
            (_QuizRequestHandler,),
            {
                "score_func": staticmethod(score_func),
                "copilot_client": copilot_client,
                "state_manager": state_manager,
                "app_config": app_config,
            },
        )

        self._server = HTTPServer((host, port), handler)
        self._port = self._server.server_address[1]

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="QuizServer",
        )
        self._thread.start()

        logger.info("QuizServer 起動: http://%s:%d", host, self._port)
        return self._port

    def stop(self) -> None:
        """HTTP サーバーを停止する。"""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            logger.info("QuizServer 停止 (port=%d)", self._port)
            self._server = None
            self._thread = None
            self._port = 0
