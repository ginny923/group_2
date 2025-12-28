import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from leaderboard import LeaderboardManager, LeaderboardScene

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
        # 直接使用武器名稱作為標籤播放
            sound.play(self.weapon.name, volume=0.3)
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

        # === [新增部分] 載入 Figma 背景圖 ===
        try:
            # 檔名需與你上傳到 GitHub 的圖片完全一致 (例如 menu_bg.jpg)
            self.background = pygame.image.load("menu_bg.png").convert()
        except:
            self.background = None 
        # ===================================

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
        # === [修改部分] 將原本的 screen.fill(BG_COLOR) 改為以下邏輯 ===
        if self.background:
            screen.blit(self.background, (0, 0)) # 繪製背景圖
        else:
            screen.fill(BG_COLOR)                # 若圖檔失效，維持原樣
        # =========================================================

        #title = self.big.render("Two Player Shooter", True, UI_COLOR)
        #screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 120))
        
        for i, it in enumerate(self.items):
            prefix = "▶ " if i == self.selection else "  "
            t = self.font.render(prefix + it, True, UI_COLOR)
            screen.blit(t, (WIDTH // 2 - 90, 260 + i * 38))

        #hint = self.font.render("Use ↑↓ and Enter", True, (170, 170, 190))
        #screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 90))

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

        # === [新增部分] 載入 Figma 背景圖 ===
        try:
            # 檔名需與你上傳到 GitHub 的圖片完全一致 (例如 menu_bg.jpg)
            self.background = pygame.image.load("menuinput_bg.png").convert()
        except:
            self.background = None 
        # ===================================

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
        # === [修改：繪製背景圖取代原本的 fill] ===
        if self.background:
            screen.blit(self.background, (0, 0))
        else:
            screen.fill(BG_COLOR)
        # ========================================

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

         # === [新增部分] 載入 Figma 背景圖 ===
        try:
            # 檔名需與你上傳到 GitHub 的圖片完全一致 (例如 menu_bg.jpg)
            self.background = pygame.image.load("mode_bg.png").convert()
        except:
            self.background = None 
        # ===================================

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

         # === [修改：繪製背景圖取代原本的 fill] ===
        if self.background:
            screen.blit(self.background, (0, 0))
        else:
            screen.fill(BG_COLOR)
        # ========================================

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

    def _draw_hp_bar(self, screen, x, y, w, h, hp, max_hp, color, label, align_right=False):
        # === [核心修改] 如果靠右，重新計算整個血條的 X 座標 ===
        # 原本傳入的 x 是左側座標，若要靠右，我們將其視為右側邊界並往左推 w
        actual_x = x - w if align_right else x
        
        # 1. 繪製底部深色邊框 (使用實際計算後的 actual_x)
        outline_rect = pygame.Rect(actual_x - 2, y - 2, w + 4, h + 4)
        pygame.draw.rect(screen, (30, 30, 35), outline_rect, border_radius=4)
        
        # 2. 繪製空槽背景
        pygame.draw.rect(screen, (50, 50, 60), (actual_x, y, w, h), border_radius=2)
        
        # 3. 計算填充寬度
        fill_w = int(w * max(0, hp) / max_hp)
        
        if fill_w > 0:
            # 判斷填充色塊的起始點
            if align_right:
                # 靠右對齊：填充色塊從「總寬度右端」開始往左填
                fill_draw_x = actual_x + (w - fill_w)
            else:
                # 靠左對齊：填充色塊從 actual_x 開始
                fill_draw_x = actual_x
            
            # 繪製主填充色
            main_fill = pygame.Rect(fill_draw_x, y, fill_w, h)
            pygame.draw.rect(screen, color, main_fill, border_radius=2)
            
            # 增加上方高光能量條
            bright_color = (min(255, color[0]+60), min(255, color[1]+60), min(255, color[2]+60))
            pygame.draw.rect(screen, bright_color, (fill_draw_x, y, fill_w, h // 3), border_radius=2)
            
            # 4. 能量刻度線 (位置固定在 actual_x 的相對位置)
            for i in range(1, 10):
                line_x = actual_x + (w * i // 10)
                pygame.draw.line(screen, (20, 20, 25), (line_x, y), (line_x, y + h - 1), 1)

        # 5. 標籤文字 (根據方向調整對齊位置)
        hp_percent = int((hp / max_hp) * 100)
        label_text = self.font.render(f"SYS_STATUS: {label.upper()}", True, (200, 200, 210))
        val_text = self.font.render(f"{hp_percent}%", True, color)
        
        if align_right:
            # 文字也靠右對齊
            screen.blit(label_text, (actual_x + w - label_text.get_width(), y - 24))
            screen.blit(val_text, (actual_x, y - 24))
        else:
            screen.blit(label_text, (actual_x, y - 24))
            screen.blit(val_text, (actual_x + w - val_text.get_width(), y - 24))

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

            # 把這個搬到最前面，確保 draw_human 抓得到它
            def rect_facing(x, y, w, h, fx):
                if fx >= 0: return pygame.Rect(x, y, w, h)
                else: return pygame.Rect(x - w, y, w, h)
                
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
            #===========
            # grenades
            for g in self.grenades:
                pygame.draw.circle(view_surf, (220, 220, 120), shift_pos(g.pos), 7)
                frac = max(0.0, min(1.0, g.fuse / GRENADE_FUSE_SEC))
                pygame.draw.circle(view_surf, (180, 180, 110), shift_pos(g.pos), int(16 * frac), 1)

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
        # --- 緊接著加入這幾行 ---
        pygame.mixer.init()                  # 啟動音效系統
        pygame.mixer.music.load("bgm.mp3")    # 載入音樂檔案 (檔名要跟資料夾裡的一樣)
        pygame.mixer.music.set_volume(0.7)    # 設定音量 (0.0 到 1.0)
        pygame.mixer.music.play(-1)           # 開始播放，-1 代表無限循環

        # 修改 Game.__init__ 內部
        self.sound = SoundManager() 
        self.sound.load("Pistol", "pistol_shot.mp3")  # 標籤名要對應武器名稱
        self.sound.load("Rifle", "rifle_shot.mp3")
        self.sound.load("Shotgun", "shotgun_shot.mp3")
        
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.render_surface = pygame.Surface((WIDTH, HEIGHT))
        pygame.display.set_caption("Two Player Shooter (OOP)")
        self.clock = pygame.time.Clock()
        self.running = True

        self.leaderboard = LeaderboardManager()

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