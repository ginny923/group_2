# play_scene.py
from __future__ import annotations
import pygame
from typing import List, Optional

# ✅ 直接從 main.py 把需要的東西「拿來用」
# 這樣你 PlayScene 內的 WIDTH/HEIGHT/ARENA_MARGIN... 都不用改
from main import (
    Scene, 
    WIDTH, HEIGHT, ARENA_MARGIN, BG_COLOR, UI_COLOR,
    P1_COLOR, P2_COLOR, OBSTACLE_COLOR,
    GRENADE_FUSE_SEC, PLAYER_SIZE,
    rects_overlap_any, safe_normalize,
    Bullet, Grenade, Explosion, Player, ArenaMap,
)

from leaderboard import LeaderboardScene
from classic_features import AppleSystem, PortalPairSystem
from hardcore_features import PoisonZoneSystem, MineSystem
from chaos_features import BarrelSystem, BreakableFloorSystem, FogOfWarSystem

import random

# =========================
# Play Scene (main game)
# =========================
class PlayScene(Scene):
    def __init__(self, game: "Game") -> None:
        self.game = game
        self.font = pygame.font.SysFont("Arial", 18)
        self.big = pygame.font.SysFont("Arial", 48, bold=True)

        mode = self.game.mode

        self.mode_hp = mode.max_hp
        self.mode_obstacles = mode.obstacle_count
        self.mode_grenade_radius = mode.grenade_radius
        self.mode_infinite_ammo = mode.infinite_ammo
        self.mode_grenade_cd = mode.grenade_cd
        self.mode_grenade_speed = mode.grenade_speed

        self.win_timer = 0.0
        self.win_delay = 1.2  # 勝利畫面停 1.2 秒後進 leaderboard

        self.world_w = mode.world_w
        self.world_h = mode.world_h

        # map
        self.map = ArenaMap(
            seed=random.randint(0, 10**9),
            obstacle_count=self.mode_obstacles,
            world_w=self.world_w,
            world_h=self.world_h
        )
        self.map.generate()

        # players
        p1_keys = dict(left=pygame.K_a, right=pygame.K_d, up=pygame.K_w, down=pygame.K_s)
        p2_keys = dict(left=pygame.K_LEFT, right=pygame.K_RIGHT, up=pygame.K_UP, down=pygame.K_DOWN)

        self.p1 = Player(
            player_id=1,
            name=self.game.p1_name,
            color=P1_COLOR,
            start_pos=(120, self.world_h // 2 - PLAYER_SIZE[1] // 2),
            keymap=p1_keys,
        )
        self.p2 = Player(
            player_id=2,
            name=self.game.p2_name,
            color=P2_COLOR,
            start_pos=(self.world_w - 120 - PLAYER_SIZE[0], self.world_h // 2 - PLAYER_SIZE[1] // 2),
            keymap=p2_keys,
        )

        # 產生出生區 avoid（避免桶/地板生成在出生點）
        spawn_left  = pygame.Rect(ARENA_MARGIN, self.world_h // 2 - 140, 260, 280)
        spawn_right = pygame.Rect(self.world_w - ARENA_MARGIN - 260, self.world_h // 2 - 140, 260, 280)
        avoid = [spawn_left, spawn_right]


        # ===== Chaos features =====
        self.barrels = None
        self.floor = None
        self.fog = None

        if self.game.mode.key == "chaos":
            self.barrels = BarrelSystem(
                world_w=self.world_w, world_h=self.world_h,
                arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                barrel_count=6
            )
            self.barrels.spawn_initial(avoid_rects=avoid)

            self.floor = BreakableFloorSystem(
                world_w=self.world_w, world_h=self.world_h,
                arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                tile_count=10
            )
            self.floor.spawn_initial(avoid_rects=avoid)

            self.fog = FogOfWarSystem(radius=220, darkness=210, feather=24)

        # -------------------------
        # ✅ Hardcore features: Poison + Mines
        # -------------------------
        self.poison = None
        self.mines = None

        if self.game.mode.key == "hardcore":
            from hardcore_features import PoisonZoneSystem, MineSystem

            # 避免地雷生成在出生點附近：用玩家出生區加大當 avoid
            avoid = [
                self.p1.rect.inflate(240, 240),
                self.p2.rect.inflate(240, 240),
            ]

            self.poison = PoisonZoneSystem(
                world_w=self.world_w,
                world_h=self.world_h,
                arena_margin=ARENA_MARGIN,
                shrink_interval=7.0,
                shrink_step=26,
                min_size=(int(self.world_w * 0.40), int(self.world_h * 0.35)),
                damage_per_sec=12.0,
            )

            self.mines = MineSystem(
                world_w=self.world_w,
                world_h=self.world_h,
                arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                mine_count=7,
                mine_radius=13,
                blast_radius=105,
                max_damage=48,
                min_damage=12,
            )
            self.mines.spawn_initial(avoid_rects=avoid)
        # ===== Classic features: apples + portals =====
        self.apple_sys = None
        self.portal_sys = None

        if self.game.mode.key == "classic":
            # 避免生成在出生區附近
            spawn_left  = pygame.Rect(ARENA_MARGIN, self.world_h // 2 - 120, 220, 240)
            spawn_right = pygame.Rect(self.world_w - ARENA_MARGIN - 220, self.world_h // 2 - 120, 220, 240)
            avoid = [spawn_left, spawn_right]

            self.apple_sys = AppleSystem(
                world_w=self.world_w, world_h=self.world_h, arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                max_apples=3,
                heal_amount=15,
                spawn_cd_range=(6.0, 10.0),
            )

            self.portal_sys = PortalPairSystem(
                world_w=self.world_w, world_h=self.world_h, arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                portal_radius=22,
                cooldown=1.0,
            )
            self.portal_sys.spawn_pair(avoid_rects=avoid)

        self.p1.max_hp = self.mode_hp
        self.p2.max_hp = self.mode_hp
        self.p1.hp = self.p1.max_hp
        self.p2.hp = self.p2.max_hp

        if self.mode_infinite_ammo:
            for pl in (self.p1, self.p2):
                for w in pl.weapons:
                    w.reserve = 9999

        self.bullets: List[Bullet] = []
        self.grenades: List[Grenade] = []
        self.explosions: List[Explosion] = []
        self.winner: Optional[str] = None

    def reset_round(self) -> None:
        self.__init__(self.game)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.game.set_scene(self.game.menu_scene_factory())
                return

            if self.winner is not None:
                if event.key == pygame.K_RETURN:
                    self.reset_round()
                return

            # P1 actions
            if event.key == pygame.K_f:
                self.bullets.extend(self.p1.try_shoot(self.game.sound))
            if event.key == pygame.K_r:
                self.p1.try_reload(self.game.sound)
            if event.key == pygame.K_q:
                g = self.p1.try_throw_grenade(self.game.sound, self.mode_grenade_speed, self.mode_grenade_cd)
                if g: self.grenades.append(g)
            # P1 weapon switch (穩定寫法)
            if event.key == pygame.K_1: self.p1.set_weapon(0)
            elif event.key == pygame.K_2: self.p1.set_weapon(1)
            elif event.key == pygame.K_3: self.p1.set_weapon(2)

            # P2 actions
            if event.key == pygame.K_SLASH:
                self.bullets.extend(self.p2.try_shoot(self.game.sound))
            if event.key == pygame.K_RSHIFT:
                self.p2.try_reload(self.game.sound)
            if event.key == pygame.K_RCTRL:
                g = self.p2.try_throw_grenade(self.game.sound, self.mode_grenade_speed, self.mode_grenade_cd)
                if g: self.grenades.append(g)
            if event.key in (pygame.K_KP1, pygame.K_KP2, pygame.K_KP3):
                # keypad '1' is 257 typically, but pygame gives constants; map directly
                if event.key == pygame.K_KP1: self.p2.set_weapon(0)
                if event.key == pygame.K_KP2: self.p2.set_weapon(1)
                if event.key == pygame.K_KP3: self.p2.set_weapon(2)

    def update(self, dt: float) -> None:
        # winner 出現後：停留一下，再去 leaderboard
        if self.winner is not None:
            self.win_timer += dt
            if self.win_timer >= self.win_delay:
                self.game.set_scene(
                    LeaderboardScene(
                        game=self.game,
                        lb=self.game.leaderboard,
                        mode_key=self.game.mode.key,
                        mode_title=self.game.mode.title,
                        winner_name=self.winner,
                        width=WIDTH,
                        height=HEIGHT,
                        bg_color=BG_COLOR,
                        ui_color=UI_COLOR,
                    )
                )
            return

        keys = pygame.key.get_pressed()

        # 取出可選系統（避免某模式沒有這些屬性就噴錯）
        barrels = getattr(self, "barrels", None)
        floor   = getattr(self, "floor", None)
        poison  = getattr(self, "poison", None)
        mines   = getattr(self, "mines", None)

        # =========================================
        # 1) 組合「障礙物清單」：地圖 + 桶子 + 坑(pit)
        # =========================================
        base_obstacles = self.map.obstacles[:]  # 原本地圖掩體
        if barrels:
            base_obstacles += barrels.get_obstacles()   # 桶子也擋路
        if floor:
            base_obstacles += floor.get_blockers()      # pit 不能走 → 也當障礙物

        # =========================================
        # 2) 玩家更新（泥地減速要先套用再更新）
        # =========================================
        for pl in (self.p1, self.p2):
            slow = floor.speed_factor_for(pl.body_hitbox()) if floor else 1.0
            old_speed = pl.speed
            pl.speed = old_speed * slow

            # ✅ 玩家碰撞用 base_obstacles（含桶子/坑）
            pl.update(dt, keys, base_obstacles, self.world_w, self.world_h)

            pl.speed = old_speed  # update 完一定要還原

        # =========================================
        # 3) 模式系統 update
        # =========================================
        # hardcore systems
        if poison:
            poison.update(dt, [self.p1, self.p2])
        if mines:
            mines.update(dt, [self.p1, self.p2])

        # classic systems
        if getattr(self, "apple_sys", None) is not None:
            spawn_left  = pygame.Rect(ARENA_MARGIN, self.world_h // 2 - 120, 220, 240)
            spawn_right = pygame.Rect(self.world_w - ARENA_MARGIN - 220, self.world_h // 2 - 120, 220, 240)
            self.apple_sys.update(dt, [self.p1, self.p2], avoid_rects=[spawn_left, spawn_right])

        if getattr(self, "portal_sys", None) is not None:
            self.portal_sys.update(dt, [self.p1, self.p2])

        # chaos systems（桶子的 fx 可能需要 update）
        if barrels:
            barrels.update(dt)

        # =========================================
        # 4) bullets：要先判斷 floor / barrel，再判斷 obstacles
        # =========================================
        for b in self.bullets[:]:
            b.update(dt)

            # remove out of arena
            if (b.rect.right < 0 or b.rect.left > self.world_w or
                b.rect.bottom < 0 or b.rect.top > self.world_h):
                self.bullets.remove(b)
                continue

            # (A) 打碎地板
            if floor and floor.handle_bullet_hit(b.rect):
                self.bullets.remove(b)
                continue

            # (B) 打到爆炸桶
            if barrels and barrels.handle_bullet_hit(b.rect, [self.p1, self.p2]):
                self.bullets.remove(b)
                self.game.sound.play("boom", volume=0.30)
                continue

            # (C) obstacle hit（用 base_obstacles，不要只用 map.obstacles）
            if rects_overlap_any(b.rect, base_obstacles):
                self.bullets.remove(b)
                continue

            # (D) player hit (no friendly-fire)
            if b.owner_id == 1 and b.rect.colliderect(self.p2.body_hitbox()):
                self.p2.take_damage(b.damage)
                self.bullets.remove(b)
                self.game.sound.play("hit", volume=0.25)
                continue

            if b.owner_id == 2 and b.rect.colliderect(self.p1.body_hitbox()):
                self.p1.take_damage(b.damage)
                self.bullets.remove(b)
                self.game.sound.play("hit", volume=0.25)
                continue

        # =========================================
        # 5) grenades：也用 base_obstacles（含桶子/坑）
        # =========================================
        for g in self.grenades[:]:
            g.update(dt, base_obstacles, self.world_w, self.world_h)

            grenade_rect = pygame.Rect(int(g.pos.x - 7), int(g.pos.y - 7), 14, 14)

            hit_p1 = (g.owner_id != 1 and grenade_rect.colliderect(self.p1.body_hitbox()))
            hit_p2 = (g.owner_id != 2 and grenade_rect.colliderect(self.p2.body_hitbox()))

            if hit_p1 or hit_p2:
                self._explode(g)
                self.grenades.remove(g)
                continue

            if g.fuse <= 0:
                self._explode(g)
                self.grenades.remove(g)

        # =========================================
        # 6) winner 判定
        # =========================================
        if not self.p1.alive():
            self.winner = self.p2.name
            self.game.leaderboard.record_win(self.game.mode.key, self.winner)
            self.win_timer = 0.0
        elif not self.p2.alive():
            self.winner = self.p1.name
            self.game.leaderboard.record_win(self.game.mode.key, self.winner)
            self.win_timer = 0.0

        # =========================================
        # 7) explosions
        # =========================================
        for e in self.explosions[:]:
            e.update(dt)
            if e.done():
                self.explosions.remove(e)

    def _explode(self, g: Grenade) -> None:
        self.game.sound.play("boom", volume=0.35)

        # ✅ 生成爆炸動畫（用模式半徑）
        self.explosions.append(
            Explosion(pos=pygame.Vector2(g.pos), max_radius=self.mode_grenade_radius, duration=0.35)
        )

        # 範圍傷害：距離越近傷害越高
        def apply(player: Player):
            d = (player.pos - g.pos).length()
            if d > self.mode_grenade_radius:
                return

            # 最高 35，最低 8（在邊緣）
            t = 1.0 - (d / self.mode_grenade_radius)
            dmg = int(8 + 27 * t)
            player.take_damage(dmg)

        apply(self.p1)
        apply(self.p2)

        if self.floor:
            self.floor.on_explosion(g.pos, self.mode_grenade_radius)

        if self.barrels:
            self.barrels.explode_at(g.pos, [self.p1, self.p2])  # 爆炸可以引爆附近桶

    def _draw_hp_bar(self, screen, x, y, w, h, hp, max_hp, color, label):
        pygame.draw.rect(screen, (60, 60, 70), (x, y, w, h), border_radius=8)
        fill_w = int(w * max(0, hp) / max_hp)
        pygame.draw.rect(screen, color, (x, y, fill_w, h), border_radius=8)
        text = self.font.render(f"{label} HP: {hp}", True, UI_COLOR)
        screen.blit(text, (x, y - 22))

    def _draw_weapon_ui(self, screen, x, y, player: Player, align_right: bool = False):
        wpn = player.weapon
        s = f"{player.name} {wpn.name}  {wpn.mag}/{wpn.reserve}"
        if wpn.reloading:
            s += "  (Reloading...)"
        s += f"  Grenade:{player.grenades_left}"
        t = self.font.render(s, True, UI_COLOR)
        if align_right:
            screen.blit(t, (x - t.get_width(), y))
        else:
            screen.blit(t, (x, y))

    def draw(self, screen: pygame.Surface) -> None:
        VIEW_W = WIDTH // 2
        VIEW_H = HEIGHT

        def clamp(v, a, b):
            return max(a, min(b, v))

        def camera_offset(center: pygame.Vector2) -> pygame.Vector2:
            off_x = center.x - VIEW_W / 2
            off_y = center.y - VIEW_H / 2
            off_x = clamp(off_x, 0, self.world_w - VIEW_W)
            off_y = clamp(off_y, 0, self.world_h - VIEW_H)
            return pygame.Vector2(off_x, off_y)

        def draw_world(view_surf: pygame.Surface, cam_off: pygame.Vector2, focus_player) -> None:
            view_surf.fill(BG_COLOR)

            def shift_rect(r: pygame.Rect) -> pygame.Rect:
                return r.move(-int(cam_off.x), -int(cam_off.y))

            def shift_pos(p: pygame.Vector2):
                return (int(p.x - cam_off.x), int(p.y - cam_off.y))
            

            def draw_human(pl: Player):
                # 人的中心（世界座標 -> 視窗座標）
                cx, cy = shift_pos(pl.pos)

                # 尺寸可以依你的 PLAYER_SIZE 調整
                body_h = 26
                body_w = 18
                head_r = 9
                leg_len = 14
                arm_len = 12

                # 讓整個人隨 facing 左右鏡像
                fx = 1 if pl.facing.x >= 0 else -1

                # 顏色（用玩家顏色）
                col = pl.color
                outline = (20, 20, 25)

                # 頭
                pygame.draw.circle(view_surf, col, (cx, cy - body_h//2 - head_r + 2), head_r)
                pygame.draw.circle(view_surf, outline, (cx, cy - body_h//2 - head_r + 2), head_r, 2)

                # 身體（圓角矩形）
                body_rect = pygame.Rect(cx - body_w//2, cy - body_h//2, body_w, body_h)
                pygame.draw.rect(view_surf, col, body_rect, border_radius=8)
                pygame.draw.rect(view_surf, outline, body_rect, width=2, border_radius=8)

                # 手（左右）
                shoulder_y = cy - body_h//2 + 8
                left_hand = (cx - body_w//2, shoulder_y)
                right_hand = (cx + body_w//2, shoulder_y)

                # 前手（朝 facing 方向那隻）
                front_hand_end = (cx + fx * (body_w//2 + arm_len), shoulder_y + 2)
                back_hand_end  = (cx - fx * (body_w//2 + arm_len - 4), shoulder_y + 6)

                pygame.draw.line(view_surf, col, left_hand, back_hand_end, 5)
                pygame.draw.line(view_surf, col, right_hand, front_hand_end, 5)

                # ===== 槍：畫在前手末端（跟著 facing）=====
                gun_color = (30, 30, 35)
                gun_outline = (220, 220, 235)

                gx, gy = front_hand_end  # 槍起點（前手末端）
                wpn = pl.weapon.name

                def rect_facing(x, y, w, h, fx):
                    """fx=1 面右: 從x往右畫；fx=-1 面左: 從x往左畫，但Rect寬度仍為正"""
                    if fx >= 0:
                        return pygame.Rect(x, y, w, h)
                    else:
                        return pygame.Rect(x - w, y, w, h)

                if wpn == "Pistol":
                    gun_rect = rect_facing(gx, gy - 3, 14, 6, fx)
                    pygame.draw.rect(view_surf, gun_color, gun_rect)
                    pygame.draw.rect(view_surf, gun_outline, gun_rect, 1)

                elif wpn == "Rifle":
                    barrel = rect_facing(gx, gy - 3, 26, 6, fx)
                    stock  = rect_facing(gx - fx * 6, gy - 2, 8, 8, fx)  # 槍托靠近身體
                    pygame.draw.rect(view_surf, gun_color, barrel)
                    pygame.draw.rect(view_surf, gun_color, stock)
                    pygame.draw.rect(view_surf, gun_outline, barrel, 1)
                    pygame.draw.rect(view_surf, gun_outline, stock, 1)

                elif wpn == "Shotgun":
                    barrel = rect_facing(gx, gy - 3, 22, 6, fx)
                    muzzle = rect_facing(gx + fx * 18, gy - 4, 6, 8, fx)  # 前端加粗
                    pygame.draw.rect(view_surf, gun_color, barrel)
                    pygame.draw.rect(view_surf, gun_color, muzzle)
                    pygame.draw.rect(view_surf, gun_outline, barrel, 1)
                    pygame.draw.rect(view_surf, gun_outline, muzzle, 1)

                # 腳
                hip_y = cy + body_h//2 - 2
                left_leg_start = (cx - 6, hip_y)
                right_leg_start = (cx + 6, hip_y)

                pygame.draw.line(view_surf, col, left_leg_start, (cx - 8, hip_y + leg_len), 6)
                pygame.draw.line(view_surf, col, right_leg_start, (cx + 8, hip_y + leg_len), 6)

                # 眼睛/方向點（用 facing）
                eye = (cx + fx * 6, cy - body_h//2 - head_r + 2)
                pygame.draw.circle(view_surf, (245, 245, 245), eye, 3)
            # arena border
            arena_rect = pygame.Rect(
                ARENA_MARGIN, ARENA_MARGIN,
                self.world_w - 2 * ARENA_MARGIN,
                self.world_h - 2 * ARENA_MARGIN
            )

            pygame.draw.rect(
                view_surf,
                (70, 70, 85),
                shift_rect(arena_rect),
                width=2,
                border_radius=14,
            )

            # obstacles
            for o in self.map.obstacles:
                pygame.draw.rect(view_surf, OBSTACLE_COLOR, shift_rect(o), border_radius=10)

            # grenades
            for g in self.grenades:
                pygame.draw.circle(view_surf, (220, 220, 120), shift_pos(g.pos), 7)
                frac = max(0.0, min(1.0, g.fuse / GRENADE_FUSE_SEC))
                pygame.draw.circle(view_surf, (180, 180, 110), shift_pos(g.pos), int(16 * frac), 1)
            # ===== Classic features draw =====
            if self.apple_sys is not None:
                self.apple_sys.draw(view_surf, shift_rect)
            if self.portal_sys is not None:
                self.portal_sys.draw(view_surf, shift_pos)
            # mines (draw under players/bullets 都可以，你想更明顯就放 players 前面)
            if self.mines:
                self.mines.draw(view_surf, shift_pos)
            # mines explosion fx
            if self.mines:
                self.mines.draw_fx(view_surf, shift_pos)
            # explosions (shockwave + core)
            for e in self.explosions:
                r = int(e.radius())
                a = e.alpha()
                # 在視窗座標的位置
                ex, ey = shift_pos(e.pos)
                # 用一個帶 alpha 的小圖層來畫（pygame.draw.circle 本身不帶 alpha）
                size = max(2, r * 2 + 8)
                fx = ex - size // 2
                fy = ey - size // 2
                surf = pygame.Surface((size, size), pygame.SRCALPHA)

                # 外圈 shockwave
                pygame.draw.circle(surf, (255, 230, 120, a), (size//2, size//2), r, 3)

                # 內核亮點（比較亮，alpha 稍高）
                core_r = max(2, int(r * 0.35))
                pygame.draw.circle(surf, (255, 200, 80, min(255, a + 40)), (size//2, size//2), core_r)

                view_surf.blit(surf, (fx, fy))

            # bullets
            for b in self.bullets:
                col = (180, 220, 255) if b.owner_id == 1 else (255, 200, 200)
                sr = shift_rect(b.rect)
                if b.kind == "line":
                    # 用速度方向畫一條線，長度用 rect.w 代表
                    dirv = safe_normalize(b.vel)
                    cx, cy = sr.center
                    half = sr.w // 2
                    p1 = (int(cx - dirv.x * half), int(cy - dirv.y * half))
                    p2 = (int(cx + dirv.x * half), int(cy + dirv.y * half))
                    pygame.draw.line(view_surf, col, p1, p2, b.thickness)
                else:
                    pygame.draw.rect(view_surf, col, sr, border_radius=4)
            # breakable floor
            if self.floor:
                self.floor.draw(view_surf, shift_rect)
            # barrels + fx
            if self.barrels:
                self.barrels.draw(view_surf, shift_rect)
                self.barrels.draw_fx(view_surf, shift_pos)

            # players（直接畫 shifted）
            for pl in (self.p1, self.p2):
                # players（成人形狀）
                draw_human(pl)

            # poison zone overlay should be late (so it darkens outside)
            if self.poison:
                self.poison.draw(view_surf, shift_rect)

            # 全部畫完後最後套 fog
            if self.fog:
                fx, fy = shift_pos(focus_player.pos)
                self.fog.apply(view_surf, (fx, fy))
        left_view = pygame.Surface((VIEW_W, VIEW_H))
        right_view = pygame.Surface((VIEW_W, VIEW_H))
        cam1 = camera_offset(self.p1.pos)
        cam2 = camera_offset(self.p2.pos)
        draw_world(left_view, cam1, self.p1)
        draw_world(right_view, cam2, self.p2)
        # 把左右畫面貼到主螢幕
        screen.fill(BG_COLOR)
        screen.blit(left_view, (0, 0))
        screen.blit(right_view, (VIEW_W, 0))
        # 中間分隔線
        pygame.draw.line(screen, (90, 90, 105), (VIEW_W, 0), (VIEW_W, HEIGHT), 2)
        # UI（沿用你原本的）
        self._draw_hp_bar(screen, 20, 26, 240, 18,
                        self.p1.hp, self.p1.max_hp, P1_COLOR,
                        self.p1.name)

        self._draw_hp_bar(screen, VIEW_W + 20, 26, 240, 18,
                        self.p2.hp, self.p2.max_hp, P2_COLOR,
                        self.p2.name)

        self._draw_weapon_ui(screen, 20, 60, self.p1, align_right=False)
        self._draw_weapon_ui(screen, WIDTH - 20, 60, self.p2, align_right=True)

        hint = self.font.render("ESC: Menu | (Win) Enter: Restart", True, (170, 170, 190))
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 32))

        if self.winner is not None:
            msg = self.big.render(f"{self.winner} WINS!", True, (245, 245, 255))
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 60))
