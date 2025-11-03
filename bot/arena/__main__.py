from __future__ import annotations

from .league_manager import LeagueManager


def main() -> None:
    manager = LeagueManager()
    manager.run_tick()
    manager.promote_winners()


if __name__ == "__main__":
    main()
