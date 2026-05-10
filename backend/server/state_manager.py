"""Unified state management for scraper and processor engines."""

from datetime import datetime
from logging import Logger
from typing import Any, Literal, Optional


class EngineState:
    """
    Manages execution state for scraper or processor engines.
    Replaces module-level mutable state dicts with a properly encapsulated class.
    """

    def __init__(self, name: str, logger: Logger) -> None:
        """Initialize state manager.

        Args:
            name: Engine name (e.g., 'scraper', 'processor')
            logger: Logger instance for file-based logging
        """
        self._name = name
        self._logger = logger
        self._state: dict[str, Any] = {}
        self._log_max_entries = 500

    def initialize(self, template: dict[str, Any]) -> None:
        """Initialize state from a template dict.

        Args:
            template: Initial state values
        """
        self._state = template.copy()
        if "log" not in self._state:
            self._state["log"] = []

    def get(self) -> dict[str, Any]:
        """Return a copy of the complete state dict."""
        return self._state.copy()

    def get_all(self) -> dict[str, Any]:
        """Return reference to internal state (use with caution)."""
        return self._state

    def update(self, **kwargs: Any) -> None:
        """Update multiple state fields atomically.

        Args:
            **kwargs: Fields to update
        """
        self._state.update(kwargs)

    def set_phase(self, phase: str) -> None:
        """Set the current execution phase."""
        self._state["phase"] = phase

    def set_running(self, running: bool) -> None:
        """Set the running state."""
        self._state["running"] = running

    def log(self, msg: str, level: Literal["info", "warn", "err"] = "info") -> None:
        """Log a message to both file and state.

        Args:
            msg: Message to log
            level: Log level ('info', 'warn', or 'err')
        """
        prefix = f"[{self._name.upper()}] "
        full_msg = prefix + msg

        # Write to file logger
        if level == "err":
            self._logger.error(msg)
        elif level == "warn":
            self._logger.warning(msg)
        else:
            self._logger.info(msg)

        # Add to state log (for UI display)
        ts = datetime.now().strftime("%H:%M:%S")
        self._state["log"].append({"ts": ts, "msg": full_msg, "level": level})

        # Trim log if it exceeds max size
        if len(self._state["log"]) > self._log_max_entries:
            self._state["log"] = self._state["log"][-self._log_max_entries :]

    def get_progress(
        self, phase: str, total_pages: int = 0, pages_done: int = 0,
        total_items: int = 0, items_done: int = 0
    ) -> float:
        """Calculate progress percentage based on phase.

        For scraper:
            - fetching phase: 0-70% based on pages
            - downloading phase: 70-100% based on items

        For processor:
            - extracting phase: 0-99% based on items

        Args:
            phase: Current phase
            total_pages: Total pages to fetch
            pages_done: Pages fetched
            total_items: Total items to process
            items_done: Items processed

        Returns:
            Progress as float between 0.0 and 1.0
        """
        if phase == "done":
            return 1.0
        if phase == "idle" or total_pages == 0 and total_items == 0:
            return 0.0
        if phase in ("fetching", "downloading"):
            if phase == "fetching" and total_pages > 0:
                return (pages_done / total_pages) * 0.7
            if phase == "downloading" and total_items > 0:
                return 0.7 + (items_done / total_items) * 0.3
        if phase == "extracting" and total_items > 0:
            return min(0.99, items_done / total_items)
        if phase == "cancelled" and total_pages > 0:
            return min(0.99, (pages_done / total_pages) * 0.7)
        return 0.0
