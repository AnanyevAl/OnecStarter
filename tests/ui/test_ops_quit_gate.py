"""Автомат выхода при активном запуске: без окна, на подменных вызовах."""

from typing import Any

from onecstarter.ui.ops.quit_dialog import QuitChoice
from onecstarter.ui.ops.quit_gate import QuitGate

WAIT_TITLE = "ждём"


class _Env:
    def __init__(self, *answers: QuitChoice, running: bool = True) -> None:
        self.running = running
        self.answers = list(answers)
        self.calls: list[str] = []
        self.title = "Оригинал"
        self.on_ask: Any = None
        self.gate = QuitGate(
            running=lambda: self.running,
            question=lambda: "вопрос",
            ask=self._ask,
            cancel_soft=lambda: self.calls.append("soft"),
            cancel_hard=lambda: self.calls.append("hard"),
            revoke_soft=lambda: self.calls.append("revoke"),
            finalize=lambda: self.calls.append("finalize"),
            quit_app=lambda: self.calls.append("quit"),
            show_window=lambda: self.calls.append("show"),
            get_title=lambda: self.title,
            set_title=self._set_title,
            wait_title=WAIT_TITLE,
        )

    def _ask(self, message: str) -> QuitChoice:
        self.calls.append("ask")
        if self.on_ask is not None:
            self.on_ask()
        return self.answers.pop(0)

    def _set_title(self, title: str) -> None:
        self.title = title

    def finish_run(self) -> None:
        self.running = False
        self.gate.on_run_finished(None)


def test_no_run_lets_the_program_quit_without_asking() -> None:
    env = _Env(running=False)
    assert env.gate.check() is True
    assert env.calls == []


def test_stay_does_not_quit_and_does_not_cancel() -> None:
    env = _Env(QuitChoice.STAY)
    assert env.gate.check() is False
    assert env.calls == ["ask"] and not env.gate.pending


def test_wait_cancels_softly_defers_quit_and_quits_after_the_run() -> None:
    env = _Env(QuitChoice.WAIT)
    assert env.gate.check() is False
    assert env.calls == ["ask", "soft", "show"] and env.gate.pending
    assert env.title == WAIT_TITLE
    env.finish_run()
    assert env.calls[-2:] == ["finalize", "quit"]


def test_abort_cancels_hard_and_quits_after_the_run() -> None:
    env = _Env(QuitChoice.ABORT)
    assert env.gate.check() is False
    assert "hard" in env.calls and "soft" not in env.calls
    env.finish_run()
    assert env.calls[-2:] == ["finalize", "quit"]


def test_second_pass_after_consent_asks_nothing_and_finalizes_nothing() -> None:
    """Правка 1: `application.quit()` шлёт closeEvent — второй проход гейта молчит."""
    env = _Env(QuitChoice.WAIT)
    env.gate.check()
    env.finish_run()
    calls_before = list(env.calls)
    assert env.gate.consented
    assert env.gate.check() is True
    assert env.calls == calls_before
    assert env.calls.count("finalize") == 1


def test_run_finishing_while_the_question_is_open_lets_the_program_quit() -> None:
    """Правка 2: сигнал конца запуска пришёл во вложенном цикле вопроса."""
    for choice in (QuitChoice.WAIT, QuitChoice.ABORT):
        env = _Env(choice)
        env.on_ask = env.finish_run  # running -> False, on_run_finished при pending == False
        assert env.gate.check() is True
        assert not env.gate.pending
        assert env.calls == ["ask"]  # ничего не отменялось, окно и заголовок не тронуты
        assert env.title == "Оригинал"
        # следующий запуск не закрывает программу
        env.running = True
        env.gate.on_run_started()
        env.finish_run()
        assert "quit" not in env.calls


def test_run_finishing_while_the_question_is_open_and_stay_keeps_the_program() -> None:
    env = _Env(QuitChoice.STAY)
    env.on_ask = env.finish_run
    assert env.gate.check() is False
    assert "quit" not in env.calls


def test_stay_after_wait_cancels_the_pending_quit_and_restores_the_title() -> None:
    """Правка 3."""
    env = _Env(QuitChoice.WAIT, QuitChoice.STAY)
    assert env.gate.check() is False
    assert env.title == WAIT_TITLE
    assert env.gate.check() is False  # второй вопрос: «Не выходить»  # noqa: RUF003
    assert not env.gate.pending
    assert env.title == "Оригинал"
    env.finish_run()
    assert "quit" not in env.calls and "finalize" not in env.calls


def test_repeated_wait_keeps_the_original_title_for_restoring() -> None:
    env = _Env(QuitChoice.WAIT, QuitChoice.WAIT, QuitChoice.STAY)
    env.gate.check()
    env.gate.check()
    env.gate.check()
    assert env.title == "Оригинал"


def test_new_run_start_resets_a_pending_quit_and_restores_the_title() -> None:
    env = _Env(QuitChoice.WAIT)
    env.gate.check()
    env.gate.on_run_started()
    assert not env.gate.pending and env.title == "Оригинал"
    env.gate.on_run_finished(None)
    assert "quit" not in env.calls


def test_stay_after_wait_revokes_the_quit_cancel() -> None:
    """Приёмка 21.11.2026, Р4 (меняет решение 15 плана 2б)."""  # noqa: RUF002
    env = _Env(QuitChoice.WAIT, QuitChoice.STAY)
    env.gate.check()
    env.gate.check()
    assert env.calls == ["ask", "soft", "show", "ask", "revoke"]


def test_stay_without_previous_wait_revokes_nothing() -> None:
    env = _Env(QuitChoice.STAY)
    env.gate.check()
    assert "revoke" not in env.calls
