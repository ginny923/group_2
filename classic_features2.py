# classic_features.py
import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame


@dataclass
class Apple:
    rect: pygame.Rect
    heal: int = 15


import math

@dataclass
class Portal:
    pos: pygame.Vector2
    base_radius: int = 22      # ✅ 基礎半徑
    phase: float = 0.0         # ✅ 每個 portal 不同相位（看起來更自然）
    amp: float = 3.0           # ✅ 跳動幅度（建議 2~5）
    freq: float = 1.4          # ✅ 跳動頻率（Hz）

    def radius(self, t: float) -> int:
        # r = base + amp * sin(2π f t + phase)
        r = self.base_radius + self.amp * math.sin(2.0 * math.pi * self.freq * t + self.phase)
        return max(6, int(r))

@dataclass
class TeleportFX:
    pos: pygame.Vector2
    max_radius: int = 34
    duration: float = 0.22
    t: float = 0.0

    def update(self, dt: float) -> None:
        self.t += dt

    def done(self) -> bool:
        return self.t >= self.duration

    def radius(self) -> int:
        p = max(0.0, min(1.0, self.t / self.duration))
        p = 1.0 - (1.0 - p) * (1.0 - p)  # ease-out
        return int(self.max_radius * p)

    def alpha(self) -> int:
        p = max(0.0, min(1.0, self.t / self.duration))
        return int(220 * (1.0 - p))


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


def _find_free_rect(
    rng: random.Random,
    world_w: int,
    world_h: int,
    arena_margin: int,
    obstacles: List[pygame.Rect],
    size: Tuple[int, int],
    avoid_rects: Optional[List[pygame.Rect]] = None,
    attempts: int = 800,
) -> Optional[pygame.Rect]:
    """找一個不撞掩體、不超出邊界的位置放物件(用rect表示)"""
    avoid_rects = avoid_rects or []
    w, h = size
    for _ in range(attempts):
        x = rng.randint(arena_margin + 10, world_w - arena_margin - 10 - w)
        y = rng.randint(arena_margin + 10, world_h - arena_margin - 10 - h)
        r = pygame.Rect(x, y, w, h)

        # 不要貼邊太近
        if r.left < arena_margin + 6 or r.right > world_w - arena_margin - 6:
            continue
        if r.top < arena_margin + 6 or r.bottom > world_h - arena_margin - 6:
            continue

        # 不要跟掩體重疊（inflate 讓它離掩體一點）
        if _rects_overlap_any(r.inflate(10, 10), obstacles):
            continue

        # 不要跟 avoid_rects 重疊（例如出生點）
        if any(r.colliderect(a.inflate(20, 20)) for a in avoid_rects):
            continue

        return r
    return None


def _find_free_point_for_portal(
    rng: random.Random,
    world_w: int,
    world_h: int,
    arena_margin: int,
    obstacles: List[pygame.Rect],
    portal_radius: int,
    avoid_rects: Optional[List[pygame.Rect]] = None,
    attempts: int = 800,
) -> Optional[pygame.Vector2]:
    """找一個不在掩體上、可放圓形傳送門中心點的位置"""
    avoid_rects = avoid_rects or []
    for _ in range(attempts):
        x = rng.randint(arena_margin + portal_radius + 10, world_w - arena_margin - portal_radius - 10)
        y = rng.randint(arena_margin + portal_radius + 10, world_h - arena_margin - portal_radius - 10)

        r = pygame.Rect(x - portal_radius, y - portal_radius, portal_radius * 2, portal_radius * 2)

        if _rects_overlap_any(r.inflate(10, 10), obstacles):
            continue
        if any(r.colliderect(a.inflate(30, 30)) for a in avoid_rects):
            continue

        return pygame.Vector2(x, y)

    return None


class AppleSystem:
    """
    Classic: 地上蘋果
    - 同時最多 max_apples（你要 3）
    - 到時間就生成一顆（若沒滿）
    - 玩家碰到 -> 回血
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        obstacles: List[pygame.Rect],
        max_apples: int = 3,
        heal_amount: int = 15,
        spawn_cd_range: Tuple[float, float] = (6.0, 10.0),
        seed: Optional[int] = None,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin
        self.obstacles = obstacles

        self.max_apples = max_apples
        self.heal_amount = heal_amount
        self.spawn_cd_range = spawn_cd_range

        self.rng = random.Random(seed)
        self.apples: List[Apple] = []

        self._spawn_t = self.rng.uniform(*self.spawn_cd_range)

    def _schedule_next(self) -> None:
        self._spawn_t = self.rng.uniform(*self.spawn_cd_range)

    def spawn_one(self, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        if len(self.apples) >= self.max_apples:
            return

        r = _find_free_rect(
            self.rng,
            self.world_w,
            self.world_h,
            self.arena_margin,
            self.obstacles,
            size=(18, 18),
            avoid_rects=avoid_rects,
        )
        if r is None:
            return

        self.apples.append(Apple(rect=r, heal=self.heal_amount))

    def update(self, dt: float, players: List[object],sound: Optional[object] = None, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        # 生成
        self._spawn_t -= dt
        if self._spawn_t <= 0:
            if len(self.apples) < self.max_apples:
                self.spawn_one(avoid_rects=avoid_rects)
            self._schedule_next()

        # 撿到判定
        for pl in players:
            # 需要 player 有 body_hitbox(), hp, max_hp
            hit = pl.body_hitbox()

            for a in self.apples[:]:
                if hit.colliderect(a.rect):
                    pl.hp = min(pl.max_hp, pl.hp + a.heal)
                    self.apples.remove(a)

                    if sound is not None:
                        sound.play("apple", volume=0.8)

    def draw(self, surf: pygame.Surface, to_view_rect: Callable[[pygame.Rect], pygame.Rect]) -> None:
        for a in self.apples:
            r = to_view_rect(a.rect)
            # 畫蘋果（紅色圓+小葉子）
            center = r.center
            pygame.draw.circle(surf, (235, 80, 80), center, 9)
            pygame.draw.circle(surf, (30, 30, 35), center, 9, 2)
            pygame.draw.circle(surf, (90, 220, 120), (center[0] + 6, center[1] - 8), 3)


class PortalPairSystem:
    """
    Classic: 1 對傳送門 A/B
    - 玩家碰到 -> 傳送到另一個
    - 每個玩家有 cooldown，避免 A<->B 連跳
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        obstacles: List[pygame.Rect],
        portal_radius: int = 22,
        cooldown: float = 1.0,
        seed: Optional[int] = None,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin
        self.obstacles = obstacles

        self.portal_radius = portal_radius
        self.cooldown = cooldown
        self.rng = random.Random(seed)

        self.A: Optional[Portal] = None
        self.B: Optional[Portal] = None

        self._t = 0.0
        self.fx: List[TeleportFX] = []

        # 每個玩家獨立冷卻
        self._cd = {1: 0.0, 2: 0.0}

    def spawn_pair(self, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        avoid_rects = avoid_rects or []

        a = _find_free_point_for_portal(
            self.rng, self.world_w, self.world_h, self.arena_margin,
            self.obstacles, self.portal_radius, avoid_rects=avoid_rects
        )
        if a is None:
            return

        b = None
        for _ in range(400):
            cand = _find_free_point_for_portal(
                self.rng, self.world_w, self.world_h, self.arena_margin,
                self.obstacles, self.portal_radius, avoid_rects=avoid_rects
            )
            if cand is None:
                continue
            if (cand - a).length() >= 220:
                b = cand
                break

        if b is None:
            # 找不到夠遠的就先用最後候選（或直接 return）
            b = _find_free_point_for_portal(
                self.rng, self.world_w, self.world_h, self.arena_margin,
                self.obstacles, self.portal_radius, avoid_rects=avoid_rects
            )
            if b is None:
                return

        self.A = Portal(
            pos=a,
            base_radius=self.portal_radius,
            phase=self.rng.random() * math.tau,
            amp=3.0,
            freq=1.4,
        )
        self.B = Portal(
            pos=b,
            base_radius=self.portal_radius,
            phase=self.rng.random() * math.tau,
            amp=3.0,
            freq=1.4,
        )

    def _inside(self, pl, portal: Portal) -> bool:
        pr = portal.radius(self._t)  # ✅ 動態半徑
        # 用玩家中心判斷
        c = pygame.Vector2(pl.rect.centerx, pl.rect.centery)
        return (c - portal.pos).length_squared() <= (pr * pr)

    def _teleport_player(self, pl, dest: Portal,sound: Optional[object] = None) -> None:

        if sound is not None:
            sound.play("teleport", volume=0.5)
        # ✅ 1) 起點特效：一定要在改位置之前
        self.fx.append(TeleportFX(pos=pygame.Vector2(pl.pos)))

        fx = 1 if getattr(pl.facing, "x", 1) >= 0 else -1

        pr = dest.radius(self._t)  # ✅ 動態半徑數值
        offset = pygame.Vector2(fx * (pr + 30), 0)

        new_center = dest.pos + offset
        pl.rect.center = (int(new_center.x), int(new_center.y))
        _clamp_rect_in_arena(pl.rect, self.world_w, self.world_h, self.arena_margin)

        if _rects_overlap_any(pl.body_hitbox(), self.obstacles):
            for dx, dy in [(0, -28), (0, 28), (28, 0), (-28, 0), (20, 20), (-20, 20), (20, -20), (-20, -20)]:
                pl.rect.center = (int(dest.pos.x + dx), int(dest.pos.y + dy))
                _clamp_rect_in_arena(pl.rect, self.world_w, self.world_h, self.arena_margin)
                if not _rects_overlap_any(pl.body_hitbox(), self.obstacles):
                    break

        pl.pos.update(pl.rect.centerx, pl.rect.centery)
        self.fx.append(TeleportFX(pos=pygame.Vector2(pl.pos)))   # 終點特效

    def update(self, dt: float, players: List[object],sound: Optional[object] = None) -> None:
        self._t += dt

        if self.A is None or self.B is None:
            return

        for pid in list(self._cd.keys()):
            self._cd[pid] = max(0.0, self._cd[pid] - dt)

        for pl in players:
            if self._cd.get(pl.id, 0.0) > 0:
                continue

            if self._inside(pl, self.A):
                self._teleport_player(pl, self.B, sound)
                self._cd[pl.id] = self.cooldown
            elif self._inside(pl, self.B):
                self._teleport_player(pl, self.A, sound)
                self._cd[pl.id] = self.cooldown

        for f in self.fx[:]:
            f.update(dt)
            if f.done():
                self.fx.remove(f)


    def draw(self, surf: pygame.Surface, shift_pos):
        # shift_pos: (world_vec2)->(x,y)

        if self.A is None or self.B is None:
            return

        for f in self.fx:
            r = f.radius()
            a = f.alpha()
            x, y = shift_pos(f.pos)

            size = r * 2 + 10
            layer = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(layer, (255, 245, 220, a), (size//2, size//2), r, 3)
            pygame.draw.circle(layer, (255, 220, 160, max(0, a-60)), (size//2, size//2), max(2, r-8), 2)
            surf.blit(layer, (x - size//2, y - size//2))

        def draw_one(p, inner, outer, glow_col):
            x, y = shift_pos(p.pos)

            # ✅ 動態半徑（呼吸動畫）
            r = p.radius(self._t)

            # ✅ alpha 光暈（跟著呼吸）
            glow_r = r + 12
            glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)

            # alpha 也跟著跳動（更有「呼吸」感）
            a = int(60 + 40 * (0.5 + 0.5 * math.sin(2.0 * math.pi * p.freq * self._t + p.phase)))
            pygame.draw.circle(glow, (*glow_col, a), (glow_r, glow_r), glow_r)

            # 先貼光暈再畫圈圈（看起來比較亮）
            surf.blit(glow, (x - glow_r, y - glow_r))

            # 外圈
            pygame.draw.circle(surf, outer, (x, y), r + 6, 4)
            # 內圈淡光
            pygame.draw.circle(surf, inner, (x, y), max(2, r - 6), 2)
            # 中心亮點
            pygame.draw.circle(surf, (220, 245, 255), (x, y), 3)
            # 黑色描邊（更清楚）
            pygame.draw.circle(surf, (20, 20, 25), (x, y), r + 6, 2)

        # A 藍紫、B 橘紅（更好辨識）
        draw_one(self.A, inner=(90, 160, 255), outer=(160, 220, 255), glow_col=(120, 190, 255))
        draw_one(self.B, inner=(255, 140, 90), outer=(255, 220, 170), glow_col=(255, 170, 120))
