import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from leaderboard import LeaderboardManager, LeaderboardScene
from classic_features import AppleSystem, PortalPairSystem

import pygame

# =========================
# Global Config
# =========================
WIDTH, HEIGHT = 1000, 600
FPS = 60

ARENA_MARGIN = 40
BG_COLOR = (18, 18, 22)
UI_COLOR = (235, 235, 245)

P1_COLOR = (70, 170, 255)
P2_COLOR = (255, 90, 90)

OBSTACLE_COLOR = (90, 90, 110)

MAX_HP = 100
PLAYER_SIZE = (44, 44)
PLAYER_SPEED = 260.0  # pixels/sec

BULLET_SIZE = (10, 4)
BULLET_SPEED = 640.0  # pixels/sec

GRENADE_RADIUS = 80
GRENADE_FUSE_SEC = 1.25
GRENADE_SPEED = 420.0
GRENADE_BOUNCE = 0.55

# 隨機掩體數量
OBSTACLE_COUNT = 9

@dataclass(frozen=True)
class GameMode:
    key: str
    title: str
    max_hp: int
    obstacle_count: int
    infinite_ammo: bool
    grenade_radius: int = GRENADE_RADIUS
    grenade_cd: float = 1.0
    grenade_speed: float = GRENADE_SPEED
    world_w: int = WIDTH
    world_h: int = HEIGHT

MODES = {
    "classic": GameMode(
        "classic", "Classic",
        max_hp=100, obstacle_count=9, grenade_radius=80,
        infinite_ammo=False, grenade_cd=1.0, grenade_speed=420,
        world_w=1400, world_h=820
    ),
    "hardcore": GameMode(
        "hardcore", "Hardcore",
        max_hp=60, obstacle_count=12, grenade_radius=95,
        infinite_ammo=False, grenade_cd=1.4, grenade_speed=460,
        world_w=1550, world_h=900
    ),
    "chaos": GameMode(
        "chaos", "Chaos",
        max_hp=120, obstacle_count=16, grenade_radius=110,
        infinite_ammo=True, grenade_cd=0.6, grenade_speed=520,
        world_w=1700, world_h=980
    ),
}


# =========================
# Utility
# =========================
def clamp_in_arena(rect: pygame.Rect, world_w: int, world_h: int) -> None:
    left = ARENA_MARGIN
    top = ARENA_MARGIN
    right = world_w - ARENA_MARGIN
    bottom = world_h - ARENA_MARGIN

    if rect.left < left: rect.left = left
    if rect.top < top: rect.top = top
    if rect.right > right: rect.right = right
    if rect.bottom > bottom: rect.bottom = bottom

    if rect.left < left: rect.left = left
    if rect.top < top: rect.top = top
    if rect.right > right: rect.right = right
    if rect.bottom > bottom: rect.bottom = bottom

def rects_overlap_any(r: pygame.Rect, rects: List[pygame.Rect]) -> bool:
    return any(r.colliderect(o) for o in rects)

def safe_normalize(v: pygame.Vector2) -> pygame.Vector2:
    if v.length_squared() == 0:
        return pygame.Vector2(0, 0)
    return v.normalize()

def angle_to_vector(deg: float) -> pygame.Vector2:
    rad = math.radians(deg)
    return pygame.Vector2(math.cos(rad), math.sin(rad))

# =========================
# Sound (fallback-safe)
# =========================
import os

class SoundManager:
    def __init__(self, master_volume: float = 0.6, channels: int = 16) -> None:
        self.sounds = {}
        self.master_volume = max(0.0, min(1.0, master_volume))

        # 預設先認為可用，下面 try 失敗再關掉
        self.enabled = True

        try:
            # mixer 可能還沒 init（有些環境 pygame.init 不一定成功 init mixer）
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.set_num_channels(channels)
        except Exception as e:
            self.enabled = False
            print(f"[SoundManager] mixer init failed: {e}")

        # 取得檔案所在資料夾，避免相對路徑問題
        self.base_dir = os.path.dirname(__file__)

    def load(self, name: str, filepath: str) -> None:
        if not self.enabled:
            self.sounds[name] = None
            return

        fullpath = filepath
        # 如果你傳入的是相對路徑，幫你變成「以程式檔所在資料夾為基準」
        if not os.path.isabs(filepath):
            fullpath = os.path.join(self.base_dir, filepath)

        try:
            self.sounds[name] = pygame.mixer.Sound(fullpath)
        except Exception as e:
            self.sounds[name] = None
            print(f"[SoundManager] load failed ({name}) {fullpath}: {e}")

    def play(self, name: str, volume: float = 0.35) -> None:
        if not self.enabled:
            return
        s = self.sounds.get(name)
        if s is None:
            return

        v = max(0.0, min(1.0, volume)) * self.master_volume
        s.set_volume(v)

        try:
            s.play()
        except Exception as e:
            print(f"[SoundManager] play failed ({name}): {e}")

# =========================
# Map / Obstacles
# =========================
class ArenaMap:
    def __init__(self, seed: Optional[int] = None, obstacle_count: int = OBSTACLE_COUNT,
                 world_w: int = WIDTH, world_h: int = HEIGHT) -> None:
        self.rng = random.Random(seed)
        self.obstacle_count = obstacle_count
        self.world_w = world_w
        self.world_h = world_h
        self.obstacles: List[pygame.Rect] = []

    def generate(self) -> None:
        self.obstacles = []

        # 固定中間柱子，幫助玩法變得有掩體節奏
        center_pillar = pygame.Rect(self.world_w // 2 - 28, self.world_h // 2 - 140, 56, 280)
        self.obstacles.append(center_pillar)

        # 生成隨機掩體，避免擋住出生點
        spawn_left  = pygame.Rect(ARENA_MARGIN, self.world_h // 2 - 120, 220, 240)
        spawn_right = pygame.Rect(self.world_w - ARENA_MARGIN - 220, self.world_h // 2 - 120, 220, 240)

        attempts = 0
        while len(self.obstacles) < 1 + self.obstacle_count and attempts < 2000:
            attempts += 1
            w = self.rng.randint(50, 150)
            h = self.rng.randint(22, 90)

            x = self.rng.randint(ARENA_MARGIN + 40, self.world_w - ARENA_MARGIN - 40 - w)
            y = self.rng.randint(ARENA_MARGIN + 40, self.world_h - ARENA_MARGIN - 40 - h)
            r = pygame.Rect(x, y, w, h)

            # 不要擋住出生區
            if r.colliderect(spawn_left) or r.colliderect(spawn_right):
                continue

            # 邊界檢查也一樣換成 self.world_w/self.world_h
            if r.right > self.world_w - ARENA_MARGIN - 10: continue
            if r.bottom > self.world_h - ARENA_MARGIN - 10: continue

            # 不要重疊太多（允許稍微靠近）
            if rects_overlap_any(r.inflate(12, 12), self.obstacles):
                continue

            self.obstacles.append(r)

    def draw(self, screen: pygame.Surface) -> None:
        for o in self.obstacles:
            pygame.draw.rect(screen, OBSTACLE_COLOR, o, border_radius=10)

# =========================
# Weapons / Projectiles
# =========================
@dataclass
class Bullet:
    rect: pygame.Rect
    vel: pygame.Vector2
    owner_id: int
    damage: int
    kind: str = "rect"      # "rect" 或 "line"
    thickness: int = 4   

    def update(self, dt: float) -> None:
        self.rect.x += int(self.vel.x * dt)
        self.rect.y += int(self.vel.y * dt)

@dataclass
class Grenade:
    pos: pygame.Vector2
    vel: pygame.Vector2
    owner_id: int
    fuse: float

    def update(self, dt: float, obstacles: List[pygame.Rect], world_w: int, world_h: int) -> None:
        # 基本移動
        self.pos += self.vel * dt

        # 簡易碰撞反彈（用一個小圓近似為 rect）
        r = pygame.Rect(int(self.pos.x - 7), int(self.pos.y - 7), 14, 14)

        # 牆壁反彈
        if r.left < ARENA_MARGIN:
            self.pos.x = ARENA_MARGIN + 7
            self.vel.x *= -GRENADE_BOUNCE
        if r.right > world_w - ARENA_MARGIN:
            self.pos.x = (world_w - ARENA_MARGIN) - 7
            self.vel.x *= -GRENADE_BOUNCE
        if r.top < ARENA_MARGIN:
            self.pos.y = ARENA_MARGIN + 7
            self.vel.y *= -GRENADE_BOUNCE
        if r.bottom > world_h - ARENA_MARGIN:
            self.pos.y = (world_h - ARENA_MARGIN) - 7
            self.vel.y *= -GRENADE_BOUNCE

        # 掩體反彈（分軸處理）
        for o in obstacles:
            if r.colliderect(o):
                # 往回推一點再反彈
                # 嘗試以最小穿透方向修正
                dx_left = abs(r.right - o.left)
                dx_right = abs(o.right - r.left)
                dy_top = abs(r.bottom - o.top)
                dy_bottom = abs(o.bottom - r.top)
                m = min(dx_left, dx_right, dy_top, dy_bottom)

                if m == dx_left:
                    self.pos.x = o.left - 7
                    self.vel.x *= -GRENADE_BOUNCE
                elif m == dx_right:
                    self.pos.x = o.right + 7
                    self.vel.x *= -GRENADE_BOUNCE
                elif m == dy_top:
                    self.pos.y = o.top - 7
                    self.vel.y *= -GRENADE_BOUNCE
                else:
                    self.pos.y = o.bottom + 7
                    self.vel.y *= -GRENADE_BOUNCE
                break

        # 簡單阻尼，避免永遠彈
        self.vel *= 0.993

        # fuse 倒數
        self.fuse -= dt

@dataclass
class Explosion:
    pos: pygame.Vector2
    max_radius: int
    duration: float = 0.35  # 爆炸動畫總時間(秒)
    t: float = 0.0          # 已經過時間

    def update(self, dt: float) -> None:
        self.t += dt

    def done(self) -> bool:
        return self.t >= self.duration

    def radius(self) -> float:
        p = max(0.0, min(1.0, self.t / self.duration))
        p = 1.0 - (1.0 - p) * (1.0 - p)  # ease-out
        return self.max_radius * p

    def alpha(self) -> int:
        p = max(0.0, min(1.0, self.t / self.duration))
        return int(255 * (1.0 - p))

class Weapon:
    """
    OOP武器：每把武器都有
    - cooldown（射速）
    - damage
    - spread（散射角度）
    - pellets（一次射出幾顆）
    - mag_size / reserve（彈匣與備彈）
    - reload_time（換彈時間）
    """
    def __init__(
        self,
        name: str,
        cooldown: float,
        damage: int,
        spread_deg: float,
        pellets: int,
        mag_size: int,
        reserve: int,
        reload_time: float,
        bullet_speed: float = BULLET_SPEED,
        bullet_size: Tuple[int, int] = (10, 4),
        bullet_kind: str = "rect",
        bullet_thickness: int = 4,
    ) -> None:
        self.name = name
        self.cooldown = cooldown
        self.damage = damage
        self.spread_deg = spread_deg
        self.pellets = pellets
        self.mag_size = mag_size
        self.bullet_speed = bullet_speed
        self.reload_time = reload_time
        self.bullet_size = bullet_size
        self.bullet_kind = bullet_kind
        self.bullet_thickness = bullet_thickness

        self.mag = mag_size
        self.reserve = reserve

        self._cooldown_left = 0.0
        self._reloading = False
        self._reload_left = 0.0

    @property
    def reloading(self) -> bool:
        return self._reloading

    def update(self, dt: float) -> None:
        if self._cooldown_left > 0:
            self._cooldown_left = max(0.0, self._cooldown_left - dt)

        if self._reloading:
            self._reload_left = max(0.0, self._reload_left - dt)
            if self._reload_left <= 0:
                self._finish_reload()

    def can_fire(self) -> bool:
        if self._reloading:
            return False
        if self._cooldown_left > 0:
            return False
        if self.mag <= 0:
            return False
        return True

    def start_reload(self) -> None:
        if self._reloading:
            return
        if self.mag == self.mag_size:
            return
        if self.reserve <= 0:
            return
        self._reloading = True
        self._reload_left = self.reload_time

    def _finish_reload(self) -> None:
        need = self.mag_size - self.mag
        take = min(need, self.reserve)
        self.mag += take
        self.reserve -= take
        self._reloading = False
        self._reload_left = 0.0

    def fire(self, origin: pygame.Vector2, dir_vec: pygame.Vector2, owner_id: int) -> List[Bullet]:
        if not self.can_fire():
            return []

        # 消耗彈匣：一次開火扣 1（霰彈槍也是扣 1）
        self.mag -= 1
        self._cooldown_left = self.cooldown

        bullets: List[Bullet] = []
        base_angle = math.degrees(math.atan2(dir_vec.y, dir_vec.x))

        for _ in range(self.pellets):
            # 隨機散射
            a = base_angle + random.uniform(-self.spread_deg, self.spread_deg)
            v = angle_to_vector(a) * self.bullet_speed

            # 子彈rect以中心建
            bw, bh = self.bullet_size
            bx = int(origin.x) - bw // 2
            by = int(origin.y) - bh // 2
            rect = pygame.Rect(bx, by, bw, bh)

            bullets.append(
                Bullet(
                    rect=rect,
                    vel=v,
                    owner_id=owner_id,
                    damage=self.damage,
                    kind=self.bullet_kind,
                    thickness=self.bullet_thickness,
                )
            )

        return bullets

def make_default_weapons() -> List[Weapon]:
    pistol = Weapon(
    name="Pistol",
    cooldown=0.22,
    damage=10,
    spread_deg=1.2,
    pellets=1,
    mag_size=12,
    reserve=48,
    reload_time=0.95,
    bullet_speed=BULLET_SPEED,
    bullet_size=(10, 5),
    bullet_kind="rect",
    )

    rifle = Weapon(
        name="Rifle",
        cooldown=0.10,
        damage=7,
        spread_deg=2.0,
        pellets=1,
        mag_size=30,
        reserve=120,
        reload_time=1.25,
        bullet_speed=BULLET_SPEED * 1.08,
        bullet_size=(26, 2),       # 細長
        bullet_kind="line",        # 用線畫（看起來更像步槍子彈）
        bullet_thickness=2,
    )

    shotgun = Weapon(
        name="Shotgun",
        cooldown=0.65,
        damage=6,
        spread_deg=9.0,
        pellets=7,
        mag_size=6,
        reserve=30,
        reload_time=1.35,
        bullet_speed=BULLET_SPEED * 0.95,
        bullet_size=(6, 6),
        bullet_kind="rect",
    )

    return [pistol, rifle, shotgun]

# =========================
# Player
# =========================
class Player:
    def __init__(
        self,
        player_id: int,
        name: str,
        color: Tuple[int, int, int],
        start_pos: Tuple[int, int],
        keymap: dict,
    ) -> None:
        self.id = player_id
        self.name = name
        self.color = color
        self.rect = pygame.Rect(start_pos[0], start_pos[1], PLAYER_SIZE[0], PLAYER_SIZE[1])
        self.pos = pygame.Vector2(self.rect.centerx, self.rect.centery)

        self.max_hp = MAX_HP
        self.hp = self.max_hp

        self.speed = PLAYER_SPEED
        self.facing = pygame.Vector2(1, 0) if player_id == 1 else pygame.Vector2(-1, 0)

        self.keymap = keymap
        self.weapons = make_default_weapons()
        self.weapon_index = 0

        self.grenade_cd = 0.0  # 手榴彈冷卻
        self.grenades_left = 3

    @property
    def weapon(self) -> Weapon:
        return self.weapons[self.weapon_index]

    def alive(self) -> bool:
        return self.hp > 0

    def body_hitbox(self) -> pygame.Rect:
        # 身體 hitbox：比整個 PLAYER_SIZE 小，讓手腳可穿牆
        w = int(self.rect.w * 0.45)   # 身體寬
        h = int(self.rect.h * 0.55)   # 身體高
        cx, cy = self.rect.center
        return pygame.Rect(cx - w // 2, cy - h // 2, w, h)

    def set_weapon(self, idx: int) -> None:
        if 0 <= idx < len(self.weapons):
            self.weapon_index = idx

    def take_damage(self, dmg: int) -> None:
        self.hp = max(0, self.hp - dmg)

    def _try_move_axis(self, dx: float, dy: float, obstacles: List[pygame.Rect],
                   world_w: int, world_h: int) -> None:
        # 分軸移動：比較滑順，也比較好卡牆
        if dx != 0:
            self.rect.x += int(dx)
            if rects_overlap_any(self.body_hitbox(), obstacles):
                self.rect.x -= int(dx)

        if dy != 0:
            self.rect.y += int(dy)
            if rects_overlap_any(self.body_hitbox(), obstacles):
                self.rect.y -= int(dy)

        clamp_in_arena(self.rect, world_w, world_h)
        self.pos.update(self.rect.centerx, self.rect.centery)

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper, obstacles: List[pygame.Rect], world_w, world_h) -> None:
        # 武器內部 cooldown / reload
        for w in self.weapons:
            w.update(dt)

        if self.grenade_cd > 0:
            self.grenade_cd = max(0.0, self.grenade_cd - dt)

        # 移動
        vx = 0.0
        vy = 0.0
        if keys[self.keymap["left"]]:  vx -= 1.0
        if keys[self.keymap["right"]]: vx += 1.0
        if keys[self.keymap["up"]]:    vy -= 1.0
        if keys[self.keymap["down"]]:  vy += 1.0

        move = safe_normalize(pygame.Vector2(vx, vy)) * self.speed * dt
        if move.length_squared() > 0:
            # 用移動方向更新 facing（讓玩家面向移動方向）
            self.facing = safe_normalize(pygame.Vector2(vx, vy))
        self._try_move_axis(move.x, move.y, obstacles, world_w, world_h)

    def try_shoot(self, sound: SoundManager) -> List[Bullet]:
        # 從玩家中心稍微往 facing 方向偏移，避免子彈出生就撞到自己
        origin = self.pos + self.facing * (PLAYER_SIZE[0] * 0.55)
        bullets = self.weapon.fire(origin=origin, dir_vec=self.facing, owner_id=self.id)
        if bullets:
            sound.play("shoot", volume=0.25)
        return bullets

    def try_reload(self, sound: SoundManager) -> None:
        before = (self.weapon.mag, self.weapon.reserve, self.weapon.reloading)
        self.weapon.start_reload()
        after = (self.weapon.mag, self.weapon.reserve, self.weapon.reloading)
        if before != after and self.weapon.reloading:
            sound.play("reload", volume=0.20)

    def try_throw_grenade(self, sound, grenade_speed, grenade_cd) -> Optional[Grenade]:
        if self.grenade_cd > 0:
            return None
        if self.grenades_left <= 0:
            return None

        self.grenade_cd = grenade_cd   # ✅ 用模式的冷卻
        self.grenades_left -= 1

        gpos = self.pos + self.facing * 24
        gvel = self.facing * grenade_speed
        sound.play("grenade", volume=0.25)
        return Grenade(pos=pygame.Vector2(gpos), vel=pygame.Vector2(gvel),
                    owner_id=self.id, fuse=GRENADE_FUSE_SEC)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, self.color, self.rect, border_radius=10)
        # facing 小白點
        tip = (int(self.pos.x + self.facing.x * 18), int(self.pos.y + self.facing.y * 18))
        pygame.draw.circle(screen, (245, 245, 245), tip, 4)

# =========================
# Scene System
# =========================
class Scene:
    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, screen: pygame.Surface) -> None:
        pass

class MenuScene(Scene):
    def __init__(self, game: "Game") -> None:
        self.game = game
        self.font = pygame.font.SysFont("Arial", 22)
        self.big = pygame.font.SysFont("Arial", 56, bold=True)
        self.selection = 0
        self.items = ["Start", "Controls", "Quit"]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selection = (self.selection - 1) % len(self.items)
            elif event.key == pygame.K_DOWN:
                self.selection = (self.selection + 1) % len(self.items)
            elif event.key == pygame.K_RETURN:
                item = self.items[self.selection]
                if item == "Start":
                    self.game.set_scene(NameInputScene(self.game))
                elif item == "Controls":
                    self.game.set_scene(ControlsScene(self.game))
                elif item == "Quit":
                    self.game.running = False

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BG_COLOR)
        title = self.big.render("Two Player Shooter", True, UI_COLOR)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 120))

        for i, it in enumerate(self.items):
            prefix = "▶ " if i == self.selection else "  "
            t = self.font.render(prefix + it, True, UI_COLOR)
            screen.blit(t, (WIDTH // 2 - 90, 260 + i * 38))

        hint = self.font.render("Use ↑↓ and Enter", True, (170, 170, 190))
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 90))

class NameInputScene(Scene):
    def __init__(self, game: "Game") -> None:
        self.game = game
        self.font = pygame.font.SysFont("Arial", 22)
        self.big = pygame.font.SysFont("Arial", 46, bold=True)

        # 目前輸入的字串
        self.names = [game.p1_name if game.p1_name != "P1" else "",
                      game.p2_name if game.p2_name != "P2" else ""]

        # 0 = P1, 1 = P2
        self.active = 0
        self.max_len = 12

        # 小游標閃爍
        self.cursor_t = 0.0
        self.cursor_on = True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            self.game.set_scene(MenuScene(self.game))
            return

        # 切換欄位
        if event.key == pygame.K_TAB:
            self.active = 1 - self.active
            return

        # 退格
        if event.key == pygame.K_BACKSPACE:
            if len(self.names[self.active]) > 0:
                self.names[self.active] = self.names[self.active][:-1]
            return

        # 確認/下一步
        if event.key == pygame.K_RETURN:
            # 若現在欄位空，先不過
            if self.names[self.active].strip() == "":
                return

            if self.active == 0:
                self.active = 1
                return

            # P2 也有了 → 存到 Game，進模式選擇
            self.game.p1_name = self.names[0].strip()
            self.game.p2_name = self.names[1].strip()
            self.game.set_scene(ModeSelectScene(self.game))
            return

        # 一般文字輸入（event.unicode）
        ch = event.unicode
        if not ch:
            return

        # 過濾不可見字元
        if ord(ch) < 32:
            return

        if len(self.names[self.active]) < self.max_len:
            self.names[self.active] += ch

    def update(self, dt: float) -> None:
        self.cursor_t += dt
        if self.cursor_t >= 0.5:
            self.cursor_t = 0.0
            self.cursor_on = not self.cursor_on

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BG_COLOR)

        title = self.big.render("Enter Player Names", True, UI_COLOR)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 90))

        hint = self.font.render("Type name | Enter: next/confirm | Tab: switch | Esc: back", True, (170, 170, 190))
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 150))

        box_w, box_h = 520, 56
        start_y = 230

        for i in range(2):
            is_active = (i == self.active)
            label = "P1 Name:" if i == 0 else "P2 Name:"
            label_surf = self.font.render(label, True, UI_COLOR)
            screen.blit(label_surf, (WIDTH // 2 - box_w // 2, start_y + i * 110 - 26))

            # box
            x = WIDTH // 2 - box_w // 2
            y = start_y + i * 110
            border = (235, 235, 245) if is_active else (120, 120, 140)
            pygame.draw.rect(screen, (35, 35, 45), (x, y, box_w, box_h), border_radius=10)
            pygame.draw.rect(screen, border, (x, y, box_w, box_h), width=2, border_radius=10)

            text = self.names[i]
            if is_active and self.cursor_on:
                text += "|"

            text_surf = self.font.render(text, True, UI_COLOR)
            screen.blit(text_surf, (x + 16, y + 15))

        ok = self.font.render("Press Enter to continue", True, (170, 170, 190))
        screen.blit(ok, (WIDTH // 2 - ok.get_width() // 2, HEIGHT - 90))

class ControlsScene(Scene):
    def __init__(self, game: "Game") -> None:
        self.game = game
        self.font = pygame.font.SysFont("Arial", 22)
        self.big = pygame.font.SysFont("Arial", 42, bold=True)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.game.set_scene(MenuScene(self.game))

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BG_COLOR)
        title = self.big.render("Controls", True, UI_COLOR)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 80))

        lines = [
            "P1 (Blue):  Move WASD | Shoot F | Reload R | Grenade Q | Weapon 1/2/3",
            "P2 (Red):   Move Arrows | Shoot / | Reload RightShift | Grenade RightCtrl | Weapon KP1/KP2/KP3",
            "Common: ESC quit | In game: ESC menu | After win: Enter restart",
        ]
        for i, s in enumerate(lines):
            t = self.font.render(s, True, UI_COLOR)
            screen.blit(t, (80, 200 + i * 40))

        hint = self.font.render("Press Enter/Esc to go back", True, (170, 170, 190))
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 90))

class ModeSelectScene(Scene):
    def __init__(self, game: "Game") -> None:
        self.game = game
        self.font = pygame.font.SysFont("Arial", 22)
        self.big = pygame.font.SysFont("Arial", 46, bold=True)

        # 顯示順序
        self.mode_keys = ["classic", "hardcore", "chaos"]
        self.selection = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.game.set_scene(MenuScene(self.game))
                return

            if event.key == pygame.K_UP:
                self.selection = (self.selection - 1) % len(self.mode_keys)
            elif event.key == pygame.K_DOWN:
                self.selection = (self.selection + 1) % len(self.mode_keys)

            elif event.key == pygame.K_RETURN:
                key = self.mode_keys[self.selection]   # "classic"/"hardcore"/"chaos"
                self.game.mode = MODES[key]            # ✅ 存 GameMode 物件
                self.game.set_scene(PlayScene(self.game))

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BG_COLOR)

        title = self.big.render("Select Mode", True, UI_COLOR)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 80))

        # 介紹文字（讓你選的時候就知道差異）
        desc_map = {
            "classic":  "Balanced: normal HP, normal obstacles, normal grenades.",
            "hardcore": "Lower HP, more obstacles, bigger grenade radius (hard).",
            "chaos":    "More HP, many obstacles, faster grenades, infinite ammo!",
        }

        desc_font = pygame.font.SysFont("Arial", 18)

        start_y = 190
        block_h = 90   # 每個模式佔 90px，高度夠就不會擠在一起

        for i, key in enumerate(self.mode_keys):
            m = MODES[key]
            prefix = "▶ " if i == self.selection else "  "

            line_surf = self.font.render(prefix + m.title, True, UI_COLOR)
            line_x = WIDTH // 2 - line_surf.get_width() // 2
            line_y = start_y + i * block_h
            screen.blit(line_surf, (line_x, line_y))

            desc_surf = desc_font.render(desc_map[key], True, (170, 170, 190))
            desc_x = WIDTH // 2 - desc_surf.get_width() // 2
            screen.blit(desc_surf, (desc_x, line_y + 28))

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
        self.win_delay = 1.2   # 勝利畫面停 1.2 秒後進 leaderboard

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

        # ===== Classic features: apples + portals =====
        self.apple_sys = None
        self.portal_sys = None

        if self.game.mode.key == "classic":
            # 避免生成在出生區附近
            spawn_left = pygame.Rect(ARENA_MARGIN, HEIGHT // 2 - 120, 220, 240)
            spawn_right = pygame.Rect(WIDTH - ARENA_MARGIN - 220, HEIGHT // 2 - 120, 220, 240)
            avoid = [spawn_left, spawn_right]

            self.apple_sys = AppleSystem(
                world_w=WIDTH, world_h=HEIGHT, arena_margin=ARENA_MARGIN,
                obstacles=self.map.obstacles,
                max_apples=3,            # ✅ 最多 3 顆
                heal_amount=15,          # 回血量
                spawn_cd_range=(6.0, 10.0),
            )

            self.portal_sys = PortalPairSystem(
                world_w=WIDTH, world_h=HEIGHT, arena_margin=ARENA_MARGIN,
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
                self.game.set_scene(MenuScene(self.game))
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
        self.p1.update(dt, keys, self.map.obstacles, self.world_w, self.world_h)
        self.p2.update(dt, keys, self.map.obstacles, self.world_w, self.world_h)

        # bullets
        for b in self.bullets[:]:
            b.update(dt)

            # remove out of arena
            if (b.rect.right < 0 or b.rect.left > self.world_w or b.rect.bottom < 0 or b.rect.top > self.world_h):
                self.bullets.remove(b)
                continue

            # obstacle hit
            if rects_overlap_any(b.rect, self.map.obstacles):
                self.bullets.remove(b)
                continue

            # player hit (no friendly-fire)
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

        # grenades (作法B：碰到人就立刻爆)
        for g in self.grenades[:]:
            g.update(dt, self.map.obstacles, self.world_w, self.world_h)

            # 手榴彈本體 hitbox（跟你 Grenade.update 用的一樣大小）
            grenade_rect = pygame.Rect(int(g.pos.x - 7), int(g.pos.y - 7), 14, 14)

            # ✅ 撞到敵人就爆（避免炸到自己：owner_id 判斷）
            hit_p1 = (g.owner_id != 1 and grenade_rect.colliderect(self.p1.body_hitbox()))
            hit_p2 = (g.owner_id != 2 and grenade_rect.colliderect(self.p2.body_hitbox()))

            if hit_p1 or hit_p2:
                self._explode(g)
                self.grenades.remove(g)
                continue

            # fuse 到了也爆
            if g.fuse <= 0:
                self._explode(g)
                self.grenades.remove(g)

        if not self.p1.alive():
            self.winner = self.p2.name
            self.game.leaderboard.record_win(self.game.mode.key, self.winner)
            self.win_timer = 0.0
        elif not self.p2.alive():
            self.winner = self.p1.name
            self.game.leaderboard.record_win(self.game.mode.key, self.winner)
            self.win_timer = 0.0

        # ===== Classic features update =====
        if self.apple_sys is not None:
            spawn_left = pygame.Rect(ARENA_MARGIN, HEIGHT // 2 - 120, 220, 240)
            spawn_right = pygame.Rect(WIDTH - ARENA_MARGIN - 220, HEIGHT // 2 - 120, 220, 240)
            self.apple_sys.update(dt, [self.p1, self.p2], avoid_rects=[spawn_left, spawn_right])

        if self.portal_sys is not None:
            self.portal_sys.update(dt, [self.p1, self.p2])

        # explosions
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

        def draw_world(view_surf: pygame.Surface, cam_off: pygame.Vector2) -> None:
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

            # players（直接畫 shifted）
            for pl in (self.p1, self.p2):
                # players（成人形狀）
                draw_human(pl)

        left_view = pygame.Surface((VIEW_W, VIEW_H))
        right_view = pygame.Surface((VIEW_W, VIEW_H))

        cam1 = camera_offset(self.p1.pos)
        cam2 = camera_offset(self.p2.pos)

        draw_world(left_view, cam1)
        draw_world(right_view, cam2)

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

# =========================
# Game Root
# =========================
class Game:
    def __init__(self) -> None:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.render_surface = pygame.Surface((WIDTH, HEIGHT))
        pygame.display.set_caption("Two Player Shooter (OOP)")
        self.clock = pygame.time.Clock()
        self.running = True

        self.leaderboard = LeaderboardManager()

        # sound (optional)
        self.sound = SoundManager()
        # 你可以放音檔到同資料夾並改成對應檔名，例如:
        # self.sound.load("shoot", "shoot.wav")
        # 這裡先用「沒有音檔也不會報錯」的方式
        self.sound.load("shoot", "shoot.wav")
        self.sound.load("reload", "reload.wav")
        self.sound.load("hit", "hit.wav")
        self.sound.load("grenade", "grenade.wav")
        self.sound.load("boom", "boom.wav")
        self.mode = MODES["classic"]
        self.p1_name = "P1"
        self.p2_name = "P2"
        self.scene: Scene = MenuScene(self)

        # 給 leaderboard scene 用的工廠（避免 leaderboard.py 反過來 import main.py）
        self.menu_scene_factory = lambda: MenuScene(self)
        self.play_scene_factory = lambda: PlayScene(self)

    def set_scene(self, scene: Scene) -> None:
        self.scene = scene

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.scene.handle_event(event)

            self.scene.update(dt)

            # 先畫到固定 1000x600 畫布
            self.scene.draw(self.render_surface)

            # 取得全螢幕大小
            sw, sh = self.screen.get_size()

            # 等比例縮放（不變形）
            scale = min(sw / WIDTH, sh / HEIGHT)
            scaled_w = int(WIDTH * scale)
            scaled_h = int(HEIGHT * scale)

            # 置中偏移（letterbox）
            ox = (sw - scaled_w) // 2
            oy = (sh - scaled_h) // 2

            # 畫背景（黑邊）
            self.screen.fill((0, 0, 0))

            # 縮放後貼到中央
            scaled = pygame.transform.smoothscale(self.render_surface, (scaled_w, scaled_h))
            self.screen.blit(scaled, (ox, oy))

            pygame.display.flip()

        pygame.quit()

def main():
    Game().run()

if __name__ == "__main__":
    main()