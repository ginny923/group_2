# hardcore_features.py
import random
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame


# -------------------------
# helpers
# -------------------------
def _rects_overlap_any(r: pygame.Rect, rects: List[pygame.Rect]) -> bool:
    return any(r.colliderect(o) for o in rects)


def _clamp_rect_in_arena(rect: pygame.Rect, world_w: int, world_h: int, arena_margin: int) -> None:
    left = arena_margin
    top = arena_margin
    right = world_w - arena_margin
    bottom = world_h - arena_margin

    if rect.left < left: rect.left = left
    if rect.top < top: rect.top = top
    if rect.right > right: rect.right = right
    if rect.bottom > bottom: rect.bottom = bottom


def _find_free_point(
    rng: random.Random,
    world_w: int,
    world_h: int,
    arena_margin: int,
    obstacles: List[pygame.Rect],
    radius: int,
    avoid_rects: Optional[List[pygame.Rect]] = None,
    attempts: int = 1200,
) -> Optional[pygame.Vector2]:
    avoid_rects = avoid_rects or []
    for _ in range(attempts):
        x = rng.randint(arena_margin + radius + 10, world_w - arena_margin - radius - 10)
        y = rng.randint(arena_margin + radius + 10, world_h - arena_margin - radius - 10)

        r = pygame.Rect(x - radius, y - radius, radius * 2, radius * 2)
        if _rects_overlap_any(r.inflate(12, 12), obstacles):
            continue
        if any(r.colliderect(a.inflate(30, 30)) for a in avoid_rects):
            continue
        return pygame.Vector2(x, y)
    return None


# -------------------------
# Poison Zone (Shrinking Safe Rect)
# -------------------------
class PoisonZoneSystem:
    """
    Hardcore: 毒圈/縮圈
    - safe_rect 代表安全區（世界座標）
    - 每 shrink_interval 秒縮一次（往內縮）
    - 玩家在 safe_rect 外：每秒扣 hp（damage_per_sec）
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        shrink_interval: float = 7.0,
        shrink_step: int = 26,
        min_size: Tuple[int, int] = (340, 220),
        damage_per_sec: float = 12.0,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin

        left = arena_margin
        top = arena_margin
        w = world_w - 2 * arena_margin
        h = world_h - 2 * arena_margin
        self.safe_rect = pygame.Rect(left, top, w, h)

        self.shrink_interval = shrink_interval
        self.shrink_step = shrink_step
        self.min_w, self.min_h = min_size
        self.damage_per_sec = damage_per_sec

        self._t = 0.0
        self._acc = 0.0

    def _shrink_once(self) -> None:
        # 往內縮（保持中心不動）
        cx, cy = self.safe_rect.center
        new_w = max(self.min_w, self.safe_rect.w - self.shrink_step * 2)
        new_h = max(self.min_h, self.safe_rect.h - self.shrink_step * 2)
        self.safe_rect.size = (new_w, new_h)
        self.safe_rect.center = (cx, cy)

        # 不要縮到超出 arena margin
        _clamp_rect_in_arena(self.safe_rect, self.world_w, self.world_h, self.arena_margin)

    def update(self, dt: float, players: List[object]) -> None:
        self._t += dt
        self._acc += dt

        if self._acc >= self.shrink_interval:
            self._acc -= self.shrink_interval
            self._shrink_once()

        # 毒傷：在安全區外扣血
        for pl in players:
            px, py = pl.rect.center
            if not self.safe_rect.collidepoint(px, py):
                # 用累積的小數避免 dt 太小扣不到
                dmg = self.damage_per_sec * dt
                # 你 Player.take_damage 是 int，這邊做累積比較準
                # 用一個私有欄位存小數
                if not hasattr(pl, "_poison_float"):
                    pl._poison_float = 0.0
                pl._poison_float += dmg
                take = int(pl._poison_float)
                if take > 0:
                    pl.take_damage(take)
                    pl._poison_float -= take

    def draw(
        self,
        surf: pygame.Surface,
        to_view_rect: Callable[[pygame.Rect], pygame.Rect],
    ) -> None:
        """
        你在 draw_world 裡面給我 to_view_rect（世界rect -> 視窗rect）
        我會：
        - 把安全區外變暗（四塊遮罩）
        - 畫安全區邊框（會有一點呼吸感）
        """
        vr = to_view_rect(self.safe_rect)

        # 1) 外面變暗（用四塊矩形遮罩，避免挖洞麻煩）
        dim = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        a = 90  # 暗度
        dim.fill((0, 0, 0, 0))

        # top
        pygame.draw.rect(dim, (0, 0, 0, a), pygame.Rect(0, 0, surf.get_width(), max(0, vr.top)))
        # bottom
        pygame.draw.rect(dim, (0, 0, 0, a), pygame.Rect(0, vr.bottom, surf.get_width(), surf.get_height() - vr.bottom))
        # left
        pygame.draw.rect(dim, (0, 0, 0, a), pygame.Rect(0, vr.top, max(0, vr.left), max(0, vr.height)))
        # right
        pygame.draw.rect(dim, (0, 0, 0, a), pygame.Rect(vr.right, vr.top, surf.get_width() - vr.right, max(0, vr.height)))

        surf.blit(dim, (0, 0))

        # 2) 安全區邊框（呼吸）
        pulse = 0.5 + 0.5 * math.sin(self._t * 2.2)
        w = 3 + int(2 * pulse)
        col = (120, 255, 170)  # 綠框
        glow = (120, 255, 170, int(40 + 60 * pulse))

        # 外光暈
        g = pygame.Surface((vr.w + 30, vr.h + 30), pygame.SRCALPHA)
        pygame.draw.rect(g, glow, pygame.Rect(15, 15, vr.w, vr.h), border_radius=14, width=8)
        surf.blit(g, (vr.x - 15, vr.y - 15))

        # 主邊框
        pygame.draw.rect(surf, col, vr, width=w, border_radius=14)


# -------------------------
# Mines
# -------------------------
@dataclass
class Mine:
    pos: pygame.Vector2
    radius: int = 13
    arm_delay: float = 0.7  # 出生後 0.7 秒才會觸發（避免一生成就踩到）
    armed: bool = False


@dataclass
class MineFX:
    pos: pygame.Vector2
    max_radius: int
    duration: float = 0.35
    t: float = 0.0

    def update(self, dt: float) -> None:
        self.t += dt

    def done(self) -> bool:
        return self.t >= self.duration

    def radius(self) -> float:
        p = max(0.0, min(1.0, self.t / self.duration))
        p = 1.0 - (1.0 - p) * (1.0 - p)
        return self.max_radius * p

    def alpha(self) -> int:
        p = max(0.0, min(1.0, self.t / self.duration))
        return int(255 * (1.0 - p))


class MineSystem:
    """
    Hardcore: 地雷
    - 地圖隨機生成 mine_count 顆
    - 玩家踩到（距離判定） -> 爆炸（範圍傷害）
    - 附帶爆炸特效（自己管理 fx）
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        obstacles: List[pygame.Rect],
        mine_count: int = 7,
        mine_radius: int = 13,
        blast_radius: int = 105,
        max_damage: int = 48,
        min_damage: int = 12,
        seed: Optional[int] = None,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin
        self.obstacles = obstacles

        self.mine_count = mine_count
        self.mine_radius = mine_radius
        self.blast_radius = blast_radius
        self.max_damage = max_damage
        self.min_damage = min_damage

        self.rng = random.Random(seed)

        self.mines: List[Mine] = []
        self.fx: List[MineFX] = []

    def spawn_initial(self, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        avoid_rects = avoid_rects or []
        self.mines = []

        for _ in range(self.mine_count):
            p = _find_free_point(
                self.rng, self.world_w, self.world_h, self.arena_margin,
                self.obstacles, radius=self.mine_radius + 6, avoid_rects=avoid_rects
            )
            if p is None:
                continue
            self.mines.append(Mine(pos=p, radius=self.mine_radius, arm_delay=0.7, armed=False))

    def _explode(self, pos: pygame.Vector2, players: List[object]) -> None:
        # 特效
        self.fx.append(MineFX(pos=pygame.Vector2(pos), max_radius=self.blast_radius, duration=0.35))

        # 範圍傷害：越近越痛
        for pl in players:
            d = (pl.pos - pos).length()
            if d > self.blast_radius:
                continue
            t = 1.0 - (d / self.blast_radius)
            dmg = int(self.min_damage + (self.max_damage - self.min_damage) * t)
            pl.take_damage(dmg)

    def update(self, dt: float, players: List[object]) -> None:
        # arm 計時
        for m in self.mines:
            if not m.armed:
                m.arm_delay -= dt
                if m.arm_delay <= 0:
                    m.armed = True

        # 踩到判定（用玩家中心距離）
        for m in self.mines[:]:
            if not m.armed:
                continue
            for pl in players:
                c = pygame.Vector2(pl.rect.centerx, pl.rect.centery)
                if (c - m.pos).length_squared() <= (m.radius + 10) ** 2:
                    # 觸發爆炸
                    self._explode(m.pos, players)
                    self.mines.remove(m)
                    break

        # fx 更新
        for e in self.fx[:]:
            e.update(dt)
            if e.done():
                self.fx.remove(e)

    def draw(self, surf: pygame.Surface, to_view_pos: Callable[[pygame.Vector2], Tuple[int, int]]) -> None:
        # 地雷本體（帶閃爍）
        t = pygame.time.get_ticks() / 1000.0

        for m in self.mines:
            x, y = to_view_pos(m.pos)

            # 外圈（armed 才亮）
            if m.armed:
                pulse = 0.5 + 0.5 * math.sin(t * 6.0)
                a = int(60 + 90 * pulse)
                glow_r = m.radius + 10
                glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 90, 90, a), (glow_r, glow_r), glow_r)
                surf.blit(glow, (x - glow_r, y - glow_r))
                core_col = (240, 90, 90)
            else:
                core_col = (120, 120, 130)

            pygame.draw.circle(surf, core_col, (x, y), m.radius)
            pygame.draw.circle(surf, (20, 20, 25), (x, y), m.radius, 2)

            # 中心點
            pygame.draw.circle(surf, (245, 245, 245), (x, y), 3)

    def draw_fx(self, surf: pygame.Surface, to_view_pos: Callable[[pygame.Vector2], Tuple[int, int]]) -> None:
        # 爆炸動畫（類似你 Explosion 的 shockwave）
        for e in self.fx:
            r = int(e.radius())
            a = e.alpha()
            x, y = to_view_pos(e.pos)

            size = max(2, r * 2 + 8)
            fx = x - size // 2
            fy = y - size // 2
            s = pygame.Surface((size, size), pygame.SRCALPHA)

            pygame.draw.circle(s, (255, 120, 120, a), (size // 2, size // 2), r, 4)
            core_r = max(2, int(r * 0.28))
            pygame.draw.circle(s, (255, 210, 180, min(255, a + 50)), (size // 2, size // 2), core_r)

            surf.blit(s, (fx, fy))
