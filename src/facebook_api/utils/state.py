import asyncio


class LoginState:
    def __init__(self) -> None:
        self.logged_in = False
        self.session_id: str | None = None
        self._event = asyncio.Event()

    def mark_logged_in(self, session_id: str) -> None:
        self.logged_in = True
        self.session_id = session_id
        self._event.set()

    async def wait_for_login(self) -> str | None:
        await self._event.wait()
        return self.session_id


login_state = LoginState()
