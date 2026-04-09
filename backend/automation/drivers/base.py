"""Abstract base class for device drivers."""

from abc import ABC, abstractmethod
from typing import Any


class AbstractDeviceDriver(ABC):
    """All device drivers must implement this interface."""

    @abstractmethod
    def run_command(self, device: Any, command: str) -> str:
        """Execute a command on the device and return output as string."""
        ...

    @abstractmethod
    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Load all available outputs for a device. Returns {key: output} dict."""
        ...
