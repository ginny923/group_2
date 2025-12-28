# leaderboard.py
import json
import os
import time
from typing import Dict, List, Optional, Tuple

import pygame


class LeaderboardManager:
    """
    每個 mode_key 一份榜單（Classic/Hardcore/Chaos 分開）
    記錄：玩家 name 的 wins 次數（累計）
    存到 leaderboard.json（跟 leaderboard.py 同資料夾）
    """
    def __init__(self, filename: str = "leaderboard.json") -> None:
        self.base_dir = os.path.dirname(__file__)
        self.path = os.path.join(self.base_dir, filename)
        self.data: Dict[str, Dict[str, Dict]] = {}  # mode_key -> name -> {"wins":int, "last":float}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self.data = raw
        except Exception as e:
            print("[Leaderboard] load failed:", e)
            self.data = {}

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[Leaderboard] save failed:", e)

    def record_win(self, mode_key: str, winner_name: str) -> None:
        mode_key = str(mode_key)
        winner_name = str(winner_name).strip()
        if not winner_name:
            return

        if mode_key not in self.data or not isinstance(self.data[mode_key], dict):
            self.data[mode_key] = {}

        if winner_name not in self.data[mode_key]:
            self.data[mode_key][winner_name] = {"wins": 0, "last": 0.0}

        self.data[mode_key][winner_name]["wins"] = int(self.data[mode_key][winner_name].get("wins", 0)) + 1
        self.data[mode_key][winner_name]["last"] = float(time.time())
        self._save()

    def top(self, mode_key: str, limit: int = 10) -> List[Tuple[str, int]]:
        """回傳 [(name, wins), ...] 依 wins 由大到小排序"""
        mode = self.data.get(mode_key, {})
        if not isinstance(mode, dict):
            return []

        items = []
        for name, info in mode.items():
            try:
                wins = int(info.get("wins", 0))
            except Exception:
                wins = 0
            items.append((name, wins))

        items.sort(key=lambda x: x[1], reverse=True)
        return items[:limit]


class LeaderboardScene:
    """
    不繼承 main.Scene 也沒關係，只要提供 handle_event/update/draw，Game 就能用。
    """
    def __init__(
        self,
        game,
        lb: LeaderboardManager,
        mode_key: str,
        mode_title: str,
        winner_name: str,
        width: int,
        height: int,
        bg_color=(18, 18, 22),
        ui_color=(235, 235, 245),
    ) -> None:
        self.game = game
        self.lb = lb
        self.mode_key = mode_key
        self.mode_title = mode_title
        self.winner_name = winner_name
        self.W = width
        self.H = height
        self.BG = bg_color
        self.UI = ui_color

        self.big = pygame.font.SysFont("Arial", 46, bold=True)
        self.font = pygame.font.SysFont("Arial", 22)
        self.small = pygame.font.SysFont("Arial", 18)

        self.rows = self.lb.top(self.mode_key, limit=10)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            # 回主選單
            # 這裡不直接 import MenuScene 避免循環依賴，用 game 自己已有的 class
            self.game.set_scene(self.game.menu_scene_factory())
            return

        if event.key == pygame.K_RETURN:
            # 再玩一次（同模式）
            self.game.set_scene(self.game.play_scene_factory())
            return

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(self.BG)

        title = self.big.render(f"Leaderboard - {self.mode_title}", True, self.UI)
        screen.blit(title, (self.W // 2 - title.get_width() // 2, 70))

        win = self.font.render(f"Winner: {self.winner_name}", True, (255, 220, 140))
        screen.blit(win, (self.W // 2 - win.get_width() // 2, 135))

        # 表格框
        box_w, box_h = 520, 330
        x = self.W // 2 - box_w // 2
        y = 190
        pygame.draw.rect(screen, (35, 35, 45), (x, y, box_w, box_h), border_radius=14)
        pygame.draw.rect(screen, (120, 120, 140), (x, y, box_w, box_h), width=2, border_radius=14)

        header = self.small.render("Rank    Name                          Wins", True, (170, 170, 190))
        screen.blit(header, (x + 22, y + 18))

        # 分隔線
        pygame.draw.line(screen, (80, 80, 100), (x + 18, y + 45), (x + box_w - 18, y + 45), 2)

        # Rows
        start_y = y + 62
        for i, (name, wins) in enumerate(self.rows):
            rank = i + 1
            highlight = (name == self.winner_name)
            col = (255, 230, 140) if highlight else self.UI

            line = self.font.render(f"{rank:>2}     {name:<28}   {wins}", True, col)
            screen.blit(line, (x + 22, start_y + i * 28))

        hint = self.small.render("Enter: Play again | Esc: Menu", True, (170, 170, 190))
        screen.blit(hint, (self.W // 2 - hint.get_width() // 2, self.H - 60))
