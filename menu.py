import json
import os
import subprocess
import sys
from dataclasses import dataclass
import time

try:
    import pygame
    from pygame import mixer
except ImportError as exc:
    raise SystemExit(
        "pygame is required for menu.py. Install it with: pip install pygame"
    ) from exc


QUESTS_FILE = "quests.json"
SAVE_DIR = "save"
PROGRESSION_FILE = os.path.join(SAVE_DIR, "progression.json")
SESSION_FILE = os.path.join(SAVE_DIR, "session_config.json")

AIRCRAFTS = [
    {"id": "f16", "name": "F-16 Falcon", "model": "models/f16"},
    {"id": "f167", "name": "F-16 Variant", "model": "models/f167"},
    {"id": "tinker", "name": "Tinker", "model": "models/tinker"},
    {"id": "ac130", "name": "AC-130", "model": "models/ac130"},
    {"id": "xwing", "name": "X-Wing", "model": "models/xwing"},
]

CONTROL_LINES = [
    "Flight: W/S pitch, A/D yaw",
    "Throttle: Q increase, E decrease",
    "Missile: M (requires lock)",
    "Guns: G",
    "Flare: F",
    "Target cycle: T / R",
    "Break lock: B",
    "Toggle cockpit: C",
    "Radar: H",
    "Zoom: Z / X / V",
    "Quit: ESC",
]


def ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    ensure_save_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def default_progression():
    return {
        "completed_nodes": [],
        "node_stars": {},
        "challenge_stars": {},
        "unlocked_aircraft": ["f16", "f167"],
        "selected_aircraft": "f167",
        "upgrades": {},
        "cosmetics": [],
    }


def load_quests():
    data = load_json(QUESTS_FILE, {})
    if "tiers" not in data or "challenges" not in data:
        raise ValueError("quests.json must include 'tiers' and 'challenges'.")
    return data


def total_stars(progression):
    return (
        sum(progression.get("node_stars", {}).values())
        + sum(progression.get("challenge_stars", {}).values())
    )


def node_index(quests):
    nodes = {}
    for tier in quests.get("tiers", []):
        for node in tier.get("nodes", []):
            nodes[node["id"]] = node
    return nodes


def node_unlocked(node, progression, nodes):
    if node.get("id") in progression.get("completed_nodes", []):
        return True

    req = node.get("unlock_requirements", {})
    req_nodes = req.get("completed_nodes", [])
    req_stars = req.get("min_stars", 0)

    completed = set(progression.get("completed_nodes", []))
    if any(n not in completed for n in req_nodes if n in nodes):
        return False
    return total_stars(progression) >= req_stars


def aircraft_unlocked(aircraft_id, progression):
    return aircraft_id in progression.get("unlocked_aircraft", [])


@dataclass
class Button:
    label: str
    rect: pygame.Rect
    on_click: object
    enabled: bool = True

    def draw(self, surface, font, hovered=False):
        if not self.enabled:
            bg = (60, 60, 60)
            fg = (145, 145, 145)
        elif hovered:
            bg = (70, 95, 150)
            fg = (255, 255, 255)
        else:
            bg = (45, 65, 100)
            fg = (225, 235, 255)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        text = font.render(self.label, True, fg)
        surface.blit(text, text.get_rect(center=self.rect.center))


def run_menu():
    pygame.init()
    mixer.init()
    mixer.music.load("models/menu_music.mp3")
    mixer.music.set_volume(0.8)
    time.sleep(0.5)  # sma
    mixer.music.play(-1)  # loop indefinitely
    pygame.display.set_caption("Flyer 101 - Mission Menu")
    screen = pygame.display.set_mode((1160, 720))
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("consolas", 44, bold=True)
    heading_font = pygame.font.SysFont("consolas", 28, bold=True)
    body_font = pygame.font.SysFont("consolas", 22)
    small_font = pygame.font.SysFont("consolas", 18)

    quests = load_quests()
    progression = load_json(PROGRESSION_FILE, default_progression())
    nodes = node_index(quests)

    selected_mode = "quests"
    selected_node_id = None
    selected_challenge_id = None

    selected_aircraft = progression.get("selected_aircraft", "f167")
    if not aircraft_unlocked(selected_aircraft, progression):
        selected_aircraft = progression.get("unlocked_aircraft", ["f16"])[0]

    selected_info = "Select a quest or challenge."
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        clicked = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = True

        screen.fill((8, 12, 18))
        pygame.draw.rect(screen, (24, 34, 52), pygame.Rect(20, 20, 1120, 680), border_radius=14)
        pygame.draw.rect(screen, (42, 62, 95), pygame.Rect(20, 20, 1120, 90), border_radius=14)

        title = title_font.render("Flyer 101 Campaign Menu", True, (240, 246, 255))
        screen.blit(title, (45, 40))
        stars_text = body_font.render(f"Total Stars: {total_stars(progression)}", True, (170, 220, 255))
        screen.blit(stars_text, (860, 53))

        buttons = []

        def add_button(x, y, w, h, label, handler, enabled=True):
            b = Button(label=label, rect=pygame.Rect(x, y, w, h), on_click=handler, enabled=enabled)
            buttons.append(b)
            return b

        # Left panel: mode + mission list
        left_panel = pygame.Rect(40, 130, 520, 540)
        pygame.draw.rect(screen, (18, 26, 38), left_panel, border_radius=12)
        pygame.draw.rect(screen, (46, 71, 105), pygame.Rect(40, 130, 520, 52), border_radius=12)
        screen.blit(heading_font.render("Mission Path", True, (235, 243, 255)), (55, 142))

        add_button(
            60,
            192,
            150,
            34,
            "Quests",
            lambda: None,
            enabled=True,
        )
        add_button(
            220,
            192,
            150,
            34,
            "Challenges",
            lambda: None,
            enabled=True,
        )

        if clicked:
            if buttons[0].rect.collidepoint(mouse_pos):
                selected_mode = "quests"
            elif buttons[1].rect.collidepoint(mouse_pos):
                selected_mode = "challenges"

        # draw mode pills manually so selected mode is obvious
        for i, mode in enumerate(("quests", "challenges")):
            rect = pygame.Rect(60 + i * 160, 192, 150, 34)
            active = selected_mode == mode
            color_bg = (80, 122, 182) if active else (40, 58, 88)
            pygame.draw.rect(screen, color_bg, rect, border_radius=8)
            label = "Quests" if mode == "quests" else "Challenges"
            screen.blit(body_font.render(label, True, (248, 252, 255)), (rect.x + 18, rect.y + 6))

        list_y = 240
        if selected_mode == "quests":
            for tier in quests.get("tiers", []):
                tier_label = f"{tier.get('id')}: {tier.get('name')}"
                screen.blit(small_font.render(tier_label, True, (170, 205, 255)), (58, list_y))
                list_y += 26
                for node in tier.get("nodes", []):
                    unlocked = node_unlocked(node, progression, nodes)
                    done = node.get("id") in progression.get("completed_nodes", [])
                    stars = progression.get("node_stars", {}).get(node.get("id"), 0)
                    prefix = "DONE" if done else ("OPEN" if unlocked else "LOCK")
                    label = f"[{prefix}] {node.get('name')}  {'*' * stars}"
                    rect = pygame.Rect(62, list_y, 480, 30)
                    color = (40, 80, 52) if done else ((45, 62, 96) if unlocked else (35, 35, 35))
                    pygame.draw.rect(screen, color, rect, border_radius=6)
                    screen.blit(small_font.render(label, True, (240, 244, 252)), (70, list_y + 7))
                    if clicked and rect.collidepoint(mouse_pos) and unlocked:
                        selected_node_id = node.get("id")
                        selected_challenge_id = None
                        selected_info = node.get("description", "")
                    list_y += 34
                list_y += 6
        else:
            for ch in quests.get("challenges", []):
                unlocked = total_stars(progression) >= ch.get("unlock_requirements", {}).get("min_stars", 0)
                stars = progression.get("challenge_stars", {}).get(ch.get("id"), 0)
                prefix = "OPEN" if unlocked else "LOCK"
                label = f"[{prefix}] {ch.get('name')}  {'*' * stars}"
                rect = pygame.Rect(62, list_y, 480, 32)
                color = (45, 62, 96) if unlocked else (35, 35, 35)
                pygame.draw.rect(screen, color, rect, border_radius=6)
                screen.blit(small_font.render(label, True, (240, 244, 252)), (70, list_y + 8))
                if clicked and rect.collidepoint(mouse_pos) and unlocked:
                    selected_challenge_id = ch.get("id")
                    selected_node_id = None
                    selected_info = ch.get("description", "")
                list_y += 36

        # Right panel: aircraft + controls + selected details
        right_panel = pygame.Rect(580, 130, 540, 540)
        pygame.draw.rect(screen, (18, 26, 38), right_panel, border_radius=12)
        pygame.draw.rect(screen, (46, 71, 105), pygame.Rect(580, 130, 540, 52), border_radius=12)
        screen.blit(heading_font.render("Loadout / Briefing", True, (235, 243, 255)), (595, 142))

        screen.blit(body_font.render("Aircraft", True, (170, 205, 255)), (600, 196))
        ay = 230
        for aircraft in AIRCRAFTS:
            unlocked = aircraft_unlocked(aircraft["id"], progression)
            active = selected_aircraft == aircraft["id"]
            rect = pygame.Rect(600, ay, 220, 30)
            color = (70, 122, 168) if active else ((40, 60, 86) if unlocked else (35, 35, 35))
            pygame.draw.rect(screen, color, rect, border_radius=6)
            lock_tag = "" if unlocked else " (locked)"
            screen.blit(small_font.render(aircraft["name"] + lock_tag, True, (245, 248, 255)), (608, ay + 7))
            if clicked and rect.collidepoint(mouse_pos) and unlocked:
                selected_aircraft = aircraft["id"]
                progression["selected_aircraft"] = selected_aircraft
                save_json(PROGRESSION_FILE, progression)
            ay += 34

        screen.blit(body_font.render("Controls", True, (170, 205, 255)), (850, 196))
        cy = 228
        for line in CONTROL_LINES:
            screen.blit(small_font.render(line, True, (220, 230, 244)), (850, cy))
            cy += 24

        screen.blit(body_font.render("Selected Mission", True, (170, 205, 255)), (600, 410))
        info_lines = [selected_info[i:i + 60] for i in range(0, len(selected_info), 60)] or ["No mission selected."]
        iy = 444
        for line in info_lines[:6]:
            screen.blit(small_font.render(line, True, (228, 236, 250)), (600, iy))
            iy += 22

        selected_ok = (
            (selected_mode == "quests" and selected_node_id is not None)
            or (selected_mode == "challenges" and selected_challenge_id is not None)
        )

        launch_rect = pygame.Rect(920, 614, 180, 38)
        launch_hover = launch_rect.collidepoint(mouse_pos)
        launch_button = Button("Launch Game", launch_rect, None, enabled=selected_ok)
        launch_button.draw(screen, body_font, hovered=launch_hover)

        if clicked and selected_ok and launch_rect.collidepoint(mouse_pos):
            selected_aircraft_model = next(
                (a["model"] for a in AIRCRAFTS if a["id"] == selected_aircraft),
                "models/f167",
            )
            session = {
                "mode": selected_mode,
                "selected_node_id": selected_node_id,
                "selected_challenge_id": selected_challenge_id,
                "selected_aircraft_id": selected_aircraft,
                "selected_aircraft_model": selected_aircraft_model,
            }
            progression["selected_aircraft"] = selected_aircraft
            save_json(PROGRESSION_FILE, progression)
            save_json(SESSION_FILE, session)
            subprocess.Popen([sys.executable, "master_of_puppets.py"])
            running = False

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    run_menu()
