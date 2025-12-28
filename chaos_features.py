# chaos_features.py
import random, math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame


# =========================
# Helpers
# =========================
def _rects_overlap_any(r: pygame.Rect, rects: List[pygame.Rect]) -> bool:
    return any(r.colliderect(o) for o in rects)

def _clamp_rect_in_arena(rect: pygame.Rect, world_w: int, world_h: int, arena_margin: int) -> None:
    left, top = arena_margin, arena_margin
    right, bottom = world_w - arena_margin, world_h - arena_margin
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
    also_avoid: Optional[List[pygame.Rect]] = None,
    attempts: int = 900,
) -> Optional[pygame.Rect]:
    avoid_rects = avoid_rects or []
    also_avoid = also_avoid or []
    w, h = size

    for _ in range(attempts):
        x = rng.randint(arena_margin + 10, world_w - arena_margin - 10 - w)
        y = rng.randint(arena_margin + 10, world_h - arena_margin - 10 - h)
        r = pygame.Rect(x, y, w, h)

        if r.left < arena_margin + 6 or r.right > world_w - arena_margin - 6:
            continue
        if r.top < arena_margin + 6 or r.bottom > world_h - arena_margin - 6:
            continue

        if _rects_overlap_any(r.inflate(10, 10), obstacles):
            continue

        if any(r.colliderect(a.inflate(24, 24)) for a in avoid_rects):
            continue

        if any(r.colliderect(a.inflate(14, 14)) for a in also_avoid):
            continue

        return r

    return None


# =========================
# 1) Explosive Barrels
# =========================
@dataclass
class Barrel:
    rect: pygame.Rect

@dataclass
class BarrelFX:
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


class BarrelSystem:
    """
    - 地圖生成 N 個桶子（像掩體）
    - 子彈打到就爆（範圍傷害 + shockwave）
    - 爆炸會引爆附近桶（chain）
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        obstacles: List[pygame.Rect],
        barrel_count: int = 6,
        barrel_size: Tuple[int, int] = (34, 46),
        blast_radius: int = 130,
        max_damage: int = 36,
        min_damage: int = 10,
        chain_radius: int = 170,
        seed: Optional[int] = None,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin
        self.obstacles = obstacles

        self.barrel_count = barrel_count
        self.barrel_size = barrel_size

        self.blast_radius = blast_radius
        self.max_damage = max_damage
        self.min_damage = min_damage
        self.chain_radius = chain_radius

        self.rng = random.Random(seed)
        self.barrels: List[Barrel] = []
        self.fx: List[BarrelFX] = []

    def get_obstacles(self) -> List[pygame.Rect]:
        return [b.rect for b in self.barrels]

    def spawn_initial(self, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        avoid_rects = avoid_rects or []
        self.barrels = []
        placed_rects: List[pygame.Rect] = []

        for _ in range(self.barrel_count):
            r = _find_free_rect(
                self.rng, self.world_w, self.world_h, self.arena_margin,
                self.obstacles,
                size=self.barrel_size,
                avoid_rects=avoid_rects,
                also_avoid=placed_rects
            )
            if r is None:
                continue
            self.barrels.append(Barrel(rect=r))
            placed_rects.append(r)

    def _apply_blast_damage(self, pos: pygame.Vector2, players: List[object]) -> None:
        for pl in players:
            d = (pl.pos - pos).length()
            if d > self.blast_radius:
                continue
            t = 1.0 - (d / self.blast_radius)
            dmg = int(self.min_damage + (self.max_damage - self.min_damage) * t)
            pl.take_damage(dmg)

    def explode_at(self, pos: pygame.Vector2, players: List[object]) -> None:
        # shockwave
        self.fx.append(BarrelFX(pos=pygame.Vector2(pos), max_radius=self.blast_radius, duration=0.35))
        self._apply_blast_damage(pos, players)

        # chain reaction
        chain = []
        for b in self.barrels:
            c = pygame.Vector2(b.rect.centerx, b.rect.centery)
            if (c - pos).length() <= self.chain_radius:
                chain.append(b)

        if chain:
            # 移除並逐個爆（避免同一桶重複爆）
            for b in chain:
                if b in self.barrels:
                    self.barrels.remove(b)
                    c = pygame.Vector2(b.rect.centerx, b.rect.centery)
                    self.fx.append(BarrelFX(pos=c, max_radius=int(self.blast_radius*0.92), duration=0.33))
                    self._apply_blast_damage(c, players)

    def handle_bullet_hit(self, bullet_rect: pygame.Rect, players: List[object]) -> bool:
        """
        在 main 的 bullet loop 裡呼叫：
        - 若子彈打到桶，回傳 True（代表你應該移除該子彈）
        """
        for b in self.barrels[:]:
            if bullet_rect.colliderect(b.rect):
                self.barrels.remove(b)
                pos = pygame.Vector2(b.rect.centerx, b.rect.centery)
                self.explode_at(pos, players)
                return True
        return False

    def update(self, dt: float) -> None:
        for e in self.fx[:]:
            e.update(dt)
            if e.done():
                self.fx.remove(e)

    def draw(self, surf: pygame.Surface, to_view_rect: Callable[[pygame.Rect], pygame.Rect]) -> None:
        for b in self.barrels:
            r = to_view_rect(b.rect)

            # 桶子本體（紅桶）
            pygame.draw.rect(surf, (210, 70, 70), r, border_radius=8)
            pygame.draw.rect(surf, (20, 20, 25), r, width=2, border_radius=8)

            # 桶環（兩條深色）
            band1 = pygame.Rect(r.x + 3, r.y + 12, r.w - 6, 6)
            band2 = pygame.Rect(r.x + 3, r.y + r.h - 18, r.w - 6, 6)
            pygame.draw.rect(surf, (150, 40, 40), band1, border_radius=6)
            pygame.draw.rect(surf, (150, 40, 40), band2, border_radius=6)

            # 危險標誌（小黃黑）
            sign = pygame.Rect(r.centerx - 7, r.centery - 7, 14, 14)
            pygame.draw.rect(surf, (235, 200, 70), sign, border_radius=3)
            pygame.draw.line(surf, (20, 20, 25), sign.topleft, sign.bottomright, 2)
            pygame.draw.line(surf, (20, 20, 25), sign.topright, sign.bottomleft, 2)

    def draw_fx(self, surf: pygame.Surface, to_view_pos: Callable[[pygame.Vector2], Tuple[int, int]]) -> None:
        # 爆炸動畫（shockwave）
        for e in self.fx:
            r = int(e.radius())
            a = e.alpha()
            x, y = to_view_pos(e.pos)

            size = max(2, r * 2 + 8)
            fx = x - size // 2
            fy = y - size // 2
            s = pygame.Surface((size, size), pygame.SRCALPHA)

            pygame.draw.circle(s, (255, 170, 80, a), (size // 2, size // 2), r, 4)
            core_r = max(2, int(r * 0.28))
            pygame.draw.circle(s, (255, 220, 170, min(255, a + 50)), (size // 2, size // 2), core_r)

            surf.blit(s, (fx, fy))


# =========================
# 2) Breakable Floor
# =========================
@dataclass
class FragileTile:
    rect: pygame.Rect
    # broken_kind: "pit" or "mud"
    broken_kind: str = "pit"
    state: str = "intact"  # "intact" | "pit" | "mud"


class BreakableFloorSystem:
    """
    - 生成一些脆弱地板（intact）
    - 被子彈打到 or 爆炸波及 -> 變 pit(不能走) 或 mud(減速)
    """
    def __init__(
        self,
        *,
        world_w: int,
        world_h: int,
        arena_margin: int,
        obstacles: List[pygame.Rect],
        tile_count: int = 10,
        size_range: Tuple[Tuple[int,int], Tuple[int,int]] = ((70, 44), (130, 70)),
        mud_slow: float = 0.72,
        initial_mud_ratio: float = 0.30,   # ✅ 新增：開局就有多少比例是泥巴
        seed: Optional[int] = None,
    ) -> None:
        self.world_w = world_w
        self.world_h = world_h
        self.arena_margin = arena_margin
        self.obstacles = obstacles

        self.tile_count = tile_count
        self.size_range = size_range
        self.mud_slow = mud_slow
        self.initial_mud_ratio = initial_mud_ratio  # ✅ 新增

        self.rng = random.Random(seed)
        self.tiles: List[FragileTile] = []

    def spawn_initial(self, avoid_rects: Optional[List[pygame.Rect]] = None) -> None:
        avoid_rects = avoid_rects or []
        self.tiles = []
        placed: List[pygame.Rect] = []

        for _ in range(self.tile_count):
            w = self.rng.randint(self.size_range[0][0], self.size_range[1][0])
            h = self.rng.randint(self.size_range[0][1], self.size_range[1][1])
            r = _find_free_rect(
                self.rng, self.world_w, self.world_h, self.arena_margin,
                self.obstacles,
                size=(w, h),
                avoid_rects=avoid_rects,
                also_avoid=placed
            )
            if r is None:
                continue

            # ✅ 先決定「開局就泥巴」(可走 + 緩速)
            if self.rng.random() < self.initial_mud_ratio:
                self.tiles.append(FragileTile(rect=r, broken_kind="mud", state="mud"))
            else:
                # 其他維持你原本：開局是 intact，之後被打碎才變 mud/pit
                kind = "mud" if (self.rng.random() < 0.45) else "pit"
                self.tiles.append(FragileTile(rect=r, broken_kind=kind, state="intact"))

            placed.append(r)


    def get_blockers(self) -> List[pygame.Rect]:
        # pit = 不能走
        return [t.rect for t in self.tiles if t.state == "pit"]

    def speed_factor_for(self, player_hitbox: pygame.Rect) -> float:
        # mud = 減速
        for t in self.tiles:
            if t.state == "mud" and player_hitbox.colliderect(t.rect):
                return self.mud_slow
        return 1.0

    def handle_bullet_hit(self, bullet_rect: pygame.Rect) -> bool:
        """
        若子彈打到脆弱地板，地板碎裂，回傳 True（代表你可以移除子彈，避免穿過）
        """
        for t in self.tiles:
            if t.state == "intact" and bullet_rect.colliderect(t.rect):
                t.state = "mud" if t.broken_kind == "mud" else "pit"
                return True
        return False

    def on_explosion(self, pos: pygame.Vector2, radius: float) -> None:
        # 爆炸波及：intact 也會碎
        for t in self.tiles:
            if t.state != "intact":
                continue
            # 距離用 tile 中心
            c = pygame.Vector2(t.rect.centerx, t.rect.centery)
            if (c - pos).length() <= radius + 20:
                t.state = "mud" if t.broken_kind == "mud" else "pit"

    def draw(self, surf: pygame.Surface, to_view_rect: Callable[[pygame.Rect], pygame.Rect]) -> None:
        import random
        import pygame

        for t in self.tiles:
            r = to_view_rect(t.rect)

            if t.state == "intact":
                # ===== 木頭地板：木色 + 木紋 + 打叉 =====
                wood_base = (140, 96, 58)     # 木板底色
                wood_edge = (60, 38, 20)      # 外框
                grain_hi  = (165, 118, 74)    # 木紋亮線
                grain_lo  = (120, 78, 45)     # 木紋暗線
                x_col     = (25, 18, 12)      # X 的顏色（深色）

                # 1) 木板底 + 外框
                pygame.draw.rect(surf, wood_base, r, border_radius=10)
                pygame.draw.rect(surf, wood_edge, r, 2, border_radius=10)

                # 2) 固定 seed：避免每幀木紋亂跳
                seed = (t.rect.x * 73856093) ^ (t.rect.y * 19349663) ^ (t.rect.w * 83492791) ^ (t.rect.h * 2654435761)
                rng = random.Random(seed)

                inner = r.inflate(-12, -12)
                if inner.width > 0 and inner.height > 0:
                    # 幾條長木紋（水平）
                    for _ in range(4):
                        y = rng.randint(inner.top, inner.bottom)
                        col = grain_hi if rng.random() < 0.5 else grain_lo
                        pygame.draw.line(surf, col, (inner.left, y), (inner.right, y), 2)

                    # 一些短刮痕
                    for _ in range(6):
                        x = rng.randint(inner.left, inner.right)
                        y = rng.randint(inner.top, inner.bottom)
                        dx = rng.randint(10, 22)
                        pygame.draw.line(surf, grain_lo, (x, y), (min(inner.right, x + dx), y), 1)

                # 3) 打叉 X
                pad = 12
                a = (r.left + pad,  r.top + pad)
                b = (r.right - pad, r.bottom - pad)
                c = (r.left + pad,  r.bottom - pad)
                d = (r.right - pad, r.top + pad)
                pygame.draw.line(surf, x_col, a, b, 4)
                pygame.draw.line(surf, x_col, c, d, 4)

            elif t.state == "pit":
                # 坑：黑洞 + 邊緣亮
                pygame.draw.rect(surf, (12, 12, 16), r, border_radius=10)
                pygame.draw.rect(surf, (110, 110, 130), r, 2, border_radius=10)

            else:  # mud
                pygame.draw.rect(surf, (120, 95, 70), r, border_radius=10)
                pygame.draw.rect(surf, (20, 20, 25), r, 2, border_radius=10)
                # 泥巴亮點（這段你原本用 self.rng 會閃；我也改成固定 seed 更穩）
                seed = (t.rect.x * 912367) ^ (t.rect.y * 3571) ^ 12345
                rng = random.Random(seed)
                for _ in range(3):
                    cx = rng.randint(r.left + 10, r.right - 10)
                    cy = rng.randint(r.top + 10, r.bottom - 10)
                    pygame.draw.circle(surf, (170, 140, 110), (cx, cy), 3)


# =========================
# 3) Fog of War (per-view)
# =========================
class FogOfWarSystem:
    """
    針對「單個視窗」做遮罩：
    - 先鋪一層黑色半透明
    - 在玩家位置挖一個洞（視野圈）
    """
    def __init__(self, radius: int = 220, darkness: int = 210, feather: int = 24) -> None:
        self.radius = radius
        self.darkness = max(0, min(255, darkness))
        self.feather = max(0, feather)

    def apply(self, view_surf: pygame.Surface, player_screen_xy: Tuple[int, int]) -> None:
        w, h = view_surf.get_size()
        x, y = player_screen_xy

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, self.darkness))

        # 挖洞（硬邊）
        pygame.draw.circle(overlay, (0, 0, 0, 0), (x, y), self.radius)

        # 羽化（外面再挖幾圈淡一點，看起來比較柔）
        if self.feather > 0:
            for i in range(1, 5):
                rr = self.radius + i * (self.feather // 4)
                aa = max(0, self.darkness - i * 35)
                pygame.draw.circle(overlay, (0, 0, 0, aa), (x, y), rr)

        view_surf.blit(overlay, (0, 0))

