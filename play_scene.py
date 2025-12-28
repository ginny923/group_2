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
            # --- 1. 背景層 (深藍底色 + 呼吸燈網格 + 星空) ---
            view_surf.fill((15, 15, 25))
            
            import math, random
            glow = math.sin(pygame.time.get_ticks() * 0.005) * 25
            g_val = max(0, min(255, 50 + glow))
            grid_color = (g_val, g_val, g_val + 20)

            grid_size = 64
            start_x = -int(cam_off.x % grid_size)
            start_y = -int(cam_off.y % grid_size)
            for gx in range(start_x, VIEW_W, grid_size):
                pygame.draw.line(view_surf, grid_color, (gx, 0), (gx, VIEW_H), 1)
            for gy in range(start_y, VIEW_H, grid_size):
                pygame.draw.line(view_surf, grid_color, (0, gy), (VIEW_W, gy), 1)

            random.seed(42)
            for _ in range(40):
                rx, ry = random.randint(0, VIEW_W), random.randint(0, VIEW_H)
                pygame.draw.circle(view_surf, (150, 150, 200), (rx, ry), 1)
            random.seed()
            #==========
            def shift_rect(r: pygame.Rect) -> pygame.Rect:
                return r.move(-int(cam_off.x), -int(cam_off.y))

            def shift_pos(p: pygame.Vector2):
                return (int(p.x - cam_off.x), int(p.y - cam_off.y))
            
            def rect_facing(x, y, w, h, fx):
                    """fx=1 面右: 從x往右畫；fx=-1 面左: 從x往左畫，但Rect寬度仍為正"""
                    if fx >= 0:
                        return pygame.Rect(x, y, w, h)
                    else:
                        return pygame.Rect(x - w, y, w, h)

            def draw_human(pl: Player):
                cx, cy = shift_pos(pl.pos)
                fx = 1 if pl.facing.x >= 0 else -1
                
                # === [修改] 顏色定義：讓 P1/P2 有區別 ===
                armor_col = (240, 240, 245)
                
                visor_col = (max(0, pl.color[0]-60), max(0, pl.color[1]-60), max(0, pl.color[2]-60))
                
                outline = (30, 30, 40)
                detail_col = (180, 185, 200)
                body_h, body_w = 26, 22
                head_r, leg_len = 12, 14

                # 1. 背包與天線 (背包顏色改用玩家色 [新增])
                tank_rect = rect_facing(cx - fx * 13, cy - 8, 10, 22, fx)
                pygame.draw.rect(view_surf, pl.color, tank_rect, border_radius=3)
                pygame.draw.rect(view_surf, outline, tank_rect, width=2, border_radius=3)
                ant_x = cx - fx * 10
                pygame.draw.line(view_surf, outline, (ant_x, cy - 5), (ant_x, cy - 35), 2)

                # 2. 身體 (不變)
                body_rect = pygame.Rect(cx - body_w//2, cy - body_h//2, body_w, body_h)
                pygame.draw.rect(view_surf, armor_col, body_rect, border_radius=6)
                pygame.draw.rect(view_surf, outline, body_rect, width=2, border_radius=6)
                panel_rect = rect_facing(cx - fx * 4, cy - 2, 8, 6, fx)
                pygame.draw.rect(view_surf, detail_col, panel_rect, border_radius=2)

                # 3. 頭部與面罩 (不變)
                head_pos = (cx, cy - body_h//2 - 6)
                pygame.draw.circle(view_surf, armor_col, head_pos, head_r)
                pygame.draw.circle(view_surf, outline, head_pos, head_r, 2)
                v_w, v_h = 14, 10
                visor_rect = rect_facing(cx + fx * 1, head_pos[1] - v_h//2, v_w, v_h, fx)
                pygame.draw.rect(view_surf, visor_col, visor_rect, border_radius=5)
                # === [修改] 將反光點改為可愛哭哭臉 ===
                # 哭哭眼睛 (兩條向下斜的線 \ / )
                eye_y = visor_rect.centery - 2
                # 左眼
                pygame.draw.line(view_surf, (255, 255, 255), 
                                 (visor_rect.centerx - 3, eye_y - 1), 
                                 (visor_rect.centerx - 1, eye_y + 1), 1)
                # 右眼
                pygame.draw.line(view_surf, (255, 255, 255), 
                                 (visor_rect.centerx + 1, eye_y + 1), 
                                 (visor_rect.centerx + 3, eye_y - 1), 1)
                
                # 委屈的小嘴巴 (一個扁平的 v)
                mouth_y = visor_rect.centery + 2
                pygame.draw.line(view_surf, (255, 255, 255), 
                                 (visor_rect.centerx - 1, mouth_y), 
                                 (visor_rect.centerx, mouth_y + 1), 1)
                pygame.draw.line(view_surf, (255, 255, 255), 
                                 (visor_rect.centerx, mouth_y + 1), 
                                 (visor_rect.centerx + 1, mouth_y), 1)
                # 3. [新增] 血量低於 30% 時，眼淚流到地板 (不變紅)
                if pl.hp / pl.max_hp < 0.3:
                    tear_col = (150, 220, 255) # 淺藍色淚水
                    floor_y = cy + 20          # 淚水流到的地板高度
                    
                    # 左眼淚痕 (從眼睛位置一直畫到地板)
                    pygame.draw.line(view_surf, tear_col, (visor_rect.centerx - 3, eye_y + 1), (visor_rect.centerx - 3, floor_y), 1)
                    # 右眼淚痕 (從眼睛位置一直畫到地板)
                    pygame.draw.line(view_surf, tear_col, (visor_rect.centerx + 3, eye_y + 1), (visor_rect.centerx + 3, floor_y), 1)
                    
                    # 在地板處畫兩個小水窪
                    pygame.draw.ellipse(view_surf, tear_col, (visor_rect.centerx - 5, floor_y - 1, 4, 2))
                    pygame.draw.ellipse(view_surf, tear_col, (visor_rect.centerx + 1, floor_y - 1, 4, 2))
                

                # === [修改後] 4. 手與武器 ===
                shoulder_y = cy - body_h//2 + 8
                # gx, gy 是槍的起點，也是手的末端
                gx = cx + (fx * (body_w//2 + 10))
                gy = shoulder_y + 2
                
                # --- 新增：畫手臂 (連結身體肩膀與槍枝) ---
                # 這樣手才會出現！使用粗線條模擬像素手臂
                pygame.draw.line(view_surf, armor_col, (cx, shoulder_y), (gx, gy), 6)
                pygame.draw.line(view_surf, outline, (cx, shoulder_y), (gx, gy), 2)

                wpn = pl.weapon.name
                g_col, g_out = (30, 30, 35), (220, 220, 235)
            # 定義未來感配色
                g_col = (40, 42, 50)      # 深灰色槍身
                g_out = (80, 85, 100)     # 槍身輪廓
                glow_col = (0, 255, 255)  # 未來感青色發光條 (能量源)

                if wpn == "Pistol":
                    # --- 未來能量手槍：短小但有厚重的能量核心 ---
                    # 主槍身
                    gr = pygame.Rect(gx if fx > 0 else gx - 16, gy - 4, 16, 8)
                    pygame.draw.rect(view_surf, g_col, gr, border_radius=2)
                    pygame.draw.rect(view_surf, g_out, gr, 1, border_radius=2)
                    # 能量發光槽 (側邊的一條細線)
                    gl = pygame.Rect(gx + (fx*4) if fx > 0 else gx - 12, gy - 1, 8, 2)
                    pygame.draw.rect(view_surf, glow_col, gl)

                elif wpn == "Rifle":
                    # --- 未來電磁步槍：長管、分段式設計 ---
                    # 前段槍管 (較細)
                    bar = pygame.Rect(gx if fx > 0 else gx - 30, gy - 2, 30, 4)
                    # 後段槍機 (較厚)
                    body = pygame.Rect(gx if fx > 0 else gx - 12, gy - 5, 12, 9)
                    # 槍托 (斜向或梯形感)
                    st = pygame.Rect((gx - fx * 8) if fx > 0 else (gx - fx * 8 - 10), gy - 3, 10, 10)
                    
                    pygame.draw.rect(view_surf, g_col, bar); pygame.draw.rect(view_surf, g_col, body)
                    pygame.draw.rect(view_surf, g_col, st, border_bottom_left_radius=4)
                    # 貫穿槍身的電磁發光線
                    line_x = gx if fx > 0 else gx - 28
                    pygame.draw.line(view_surf, glow_col, (line_x, gy), (line_x + (fx*25 if fx > 0 else 25), gy), 1)
                    # 輪廓
                    pygame.draw.rect(view_surf, g_out, bar, 1); pygame.draw.rect(view_surf, g_out, body, 1)

                elif wpn == "Shotgun":
                    # --- 未來重型霰彈槍：寬大槍口、帶有散熱片感 ---
                    # 厚重的槍身
                    bar = pygame.Rect(gx if fx > 0 else gx - 24, gy - 5, 24, 10)
                    # 槍口加寬處理 (散熱器)
                    muz = pygame.Rect((gx + fx * 16) if fx > 0 else (gx + fx * 16 - 8), gy - 7, 8, 14)
                    
                    pygame.draw.rect(view_surf, g_col, bar, border_radius=1)
                    pygame.draw.rect(view_surf, (50, 55, 70), muz) # 槍口用不同深灰色
                    # 側面三個能量指示燈 (點點)
                    for i in range(3):
                        dot_x = gx + fx*(4 + i*4) if fx > 0 else gx - (6 + i*4)
                        pygame.draw.circle(view_surf, glow_col, (dot_x, gy), 1)
                    # 輪廓
                    pygame.draw.rect(view_surf, g_out, bar, 1); pygame.draw.rect(view_surf, g_out, muz, 1)

                # === [修改] 5. 腳部：加入走路擺動動畫 [新增] ===
                import math
                # 使用 pygame.time.get_ticks() 根據時間產生波動
                # 只有在速度不為 0 時才擺動 (或簡單點讓它一直動也行)
                walk_swing = math.sin(pygame.time.get_ticks() * 0.015) * 6
                
                hip_y = cy + body_h//2 - 2
                # 左腳
                pygame.draw.line(view_surf, armor_col, (cx - 7, hip_y), (cx - 9, hip_y + leg_len + walk_swing), 8)
                pygame.draw.line(view_surf, outline, (cx - 7, hip_y), (cx - 9, hip_y + leg_len + walk_swing), 2)
                # 右腳 (擺動方向相反)
                pygame.draw.line(view_surf, armor_col, (cx + 7, hip_y), (cx + 9, hip_y + leg_len - walk_swing), 8)
                pygame.draw.line(view_surf, outline, (cx + 7, hip_y), (cx + 9, hip_y + leg_len - walk_swing), 2)

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

            # obstacles (磚塊風格)
            for o in self.map.obstacles:
                r = shift_rect(o)
                
                # 1. 畫出障礙物底色（磚縫/水泥的顏色）
                grout_color = (40, 40, 45) # 深灰色磚縫
                pygame.draw.rect(view_surf, grout_color, r, border_radius=4)
                
                # 2. 定義磚塊大小
                brick_w = 20  # 磚塊寬度
                brick_h = 10  # 磚塊高度
                
                # 3. 遍歷矩形區域畫出每一塊小磚頭
                for row_y in range(r.top, r.bottom, brick_h):
                    # 計算這一行是否需要偏移（交錯排列效果）
                    # 使用 row_y 相對於 r.top 的索引來判斷奇偶行
                    is_offset = ((row_y - r.top) // brick_h) % 2 == 1
                    start_x = r.left - (brick_w // 2 if is_offset else 0)
                    
                    for col_x in range(start_x, r.right, brick_w):
                        # 計算單個磚塊的矩形
                        b_rect = pygame.Rect(col_x + 1, row_y + 1, brick_w - 2, brick_h - 2)
                        
                        # 確保磚塊不超出障礙物邊界
                        clipped_rect = b_rect.clip(r)
                        
                        if clipped_rect.width > 0 and clipped_rect.height > 0:
                            # 磚塊主色 (根據原本的 OBSTACLE_COLOR 做一點隨機或明暗變化)
                            pygame.draw.rect(view_surf, OBSTACLE_COLOR, clipped_rect, border_radius=2)
                            
                            # 加上磚塊的高光（左上角），增加立體感
                            highlight_col = (min(255, OBSTACLE_COLOR[0]+30), 
                                             min(255, OBSTACLE_COLOR[1]+30), 
                                             min(255, OBSTACLE_COLOR[2]+30))
                            pygame.draw.line(view_surf, highlight_col, 
                                             clipped_rect.topleft, (clipped_rect.right, clipped_rect.top), 1)
                            pygame.draw.line(view_surf, highlight_col, 
                                             clipped_rect.topleft, (clipped_rect.left, clipped_rect.bottom), 1)

                # 4. 最後加上一層外框，讓整體更紮實
                pygame.draw.rect(view_surf, (20, 20, 25), r, width=2, border_radius=4)
            
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
