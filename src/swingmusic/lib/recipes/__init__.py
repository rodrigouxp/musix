"""
Recipes are a way to create homepage rows.
"""

from typing import Any, List
from abc import ABC, abstractmethod


class HomepageRoutine(ABC):
    """
    A routine creates a row of homepage items.
    """

    @property
    @abstractmethod
    def is_valid(self) -> bool: ...

    def __init__(self) -> None:
        if not self.is_valid:
            return

        self.run()

    @abstractmethod
    def run(self) -> List[Any]:
        """
        Creates the homepage items and saves them to the
        homepage store if self.is_valid is true.
        """
        ...
