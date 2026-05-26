from .wezterm_cli import WezTermCLI


class Commander:
    """Receives command dispatch requests and injects them into WezTerm panes.

    The default mode (execute_immediately=False) implements the HITL gate:
    the command is placed into the pane's input area but the user must
    manually press Enter to execute.
    """

    def __init__(self, cli: WezTermCLI | None = None):
        self._cli = cli or WezTermCLI()

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def draft_cli_command(
        self,
        pane_id: int | str,
        command: str,
        execute_immediately: bool = False,
    ) -> bool:
        """Inject a command into the target pane's input area.

        By default, no trailing newline is sent -- the HITL gate requires
        the user to visually confirm and press Enter manually.

        If execute_immediately is True, Enter is automatically sent.
        """
        ok = self._cli.send_text(pane_id, command)
        if not ok:
            print(f"[Commander] Failed to inject command into pane {pane_id}")
            return False

        if execute_immediately:
            return self._cli.send_enter(pane_id)

        return True

    # ------------------------------------------------------------------
    # Pane discovery (convenience passthrough)
    # ------------------------------------------------------------------

    def list_panes(self) -> list[dict]:
        return self._cli.list_panes()
