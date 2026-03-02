from ursina import *
from ursina import Quat
import random, math, time
import os, sys
from copy import deepcopy
from ursina.prefabs.trail_renderer import TrailRenderer
import socket, json, threading, uuid
game_paused = True
def start_game():
    global game_paused
    game_paused = False
y = 4
Text.default_font = "models/orbitron.ttf"

SAVE_DIR = "save"
PROGRESSION_FILE = os.path.join(SAVE_DIR, "progression.json")
SESSION_FILE = os.path.join(SAVE_DIR, "session_config.json")
QUESTS_FILE = "quests.json"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
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


def load_quests(path=QUESTS_FILE):
    return load_json(path, {"tiers": [], "challenges": []})


def iter_quest_nodes(quests_data):
    for tier in quests_data.get("tiers", []):
        for node in tier.get("nodes", []):
            yield node


def find_quest_node(node_id, quests_data):
    for node in iter_quest_nodes(quests_data):
        if node.get("id") == node_id:
            return node
    return None


def find_challenge(challenge_id, quests_data):
    for challenge in quests_data.get("challenges", []):
        if challenge.get("id") == challenge_id:
            return challenge
    return None


def load_missions(path="missions/missions.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    missions_data = data.get("missions", [])
    if not isinstance(missions_data, list):
        raise ValueError("missions.json format error: 'missions' must be a list")
    return missions_data


def _build_mission_briefing_text(selected_mission):
    objective_lines = []
    for i, objective in enumerate(selected_mission.get("objectives", []), start=1):
        objective_text = objective.get("description", "No objective description")
        objective_lines.append(f"{i}. {objective_text}")
    optional_lines = []
    for i, objective in enumerate(selected_mission.get("optional_objectives", []), start=1):
        optional_lines.append(f"{i}. {objective.get('description', 'Optional objective')}")
    fail_lines = selected_mission.get("fail_conditions", [])

    objectives_block = "\n".join(objective_lines) if objective_lines else "No objectives"
    optional_block = "\n".join(optional_lines) if optional_lines else "None"
    fail_block = "\n".join([f"- {line}" for line in fail_lines]) if fail_lines else "None"
    bonus_time = selected_mission.get("bonus_time")
    bonus_text = f"{bonus_time}s" if bonus_time else "N/A"
    return (
        f"\n=== MISSION BRIEFING ===\n"
        f"Mission: {selected_mission.get('name', 'Unknown Mission')}\n\n"
        f"Briefing: {selected_mission.get('description', 'No briefing available')}\n\n"
        f"Objectives:\n{objectives_block}\n\n"
        f"Optional Objectives:\n{optional_block}\n\n"
        f"Fail Conditions:\n{fail_block}\n\n"
        f"Bonus Time: {bonus_text}"
    )


quests_data = load_quests()
progression = load_json(PROGRESSION_FILE, default_progression())
progression.setdefault("completed_nodes", [])
progression.setdefault("node_stars", {})
progression.setdefault("challenge_stars", {})
progression.setdefault("unlocked_aircraft", ["f16", "f167"])
progression.setdefault("selected_aircraft", "f167")
progression.setdefault("upgrades", {})
progression.setdefault("cosmetics", [])
current_session = load_json(SESSION_FILE, {})
session_mode = current_session.get("mode", "random")
selected_node_id = current_session.get("selected_node_id")
selected_challenge_id = current_session.get("selected_challenge_id")
selected_aircraft_model = current_session.get("selected_aircraft_model")
selected_aircraft_id = current_session.get("selected_aircraft_id", progression.get("selected_aircraft", "f167"))
aircraft_models = {
    "f16": "models/f16",
    "f167": "models/f167",
    "tinker": "models/tinker",
    "ac130": "models/ac130",
    "xwing": "models/xwing",
}
if not selected_aircraft_model:
    selected_aircraft_model = aircraft_models.get(selected_aircraft_id, "models/f167")

active_node = find_quest_node(selected_node_id, quests_data) if session_mode == "quests" else None
active_challenge = find_challenge(selected_challenge_id, quests_data) if session_mode == "challenges" else None
difficulty_scale = 1.0
active_mission_id = None
active_mission_type = "random"

if active_node:
    mission = deepcopy(active_node.get("mission", {}))
    difficulty_scale = float(active_node.get("difficulty_scale", 1.0))
    active_mission_id = active_node.get("id")
    active_mission_type = "quest"
elif active_challenge:
    mission = deepcopy(active_challenge.get("mission", {}))
    difficulty_scale = float(active_challenge.get("difficulty_scale", 1.0))
    active_mission_id = active_challenge.get("id")
    active_mission_type = "challenge"
else:
    missions = load_missions()
    if not missions:
        raise ValueError("No missions found in missions/missions.json")
    mission = random.choice(missions).copy()

mission["objectives"] = [obj.copy() for obj in mission.get("objectives", [])]
initial_enemy_count_override = mission.get("enemy_spawn_count")



missiles = []
enemy_planes = []
flares = []
# Offscreen enemy arrows (HUD)
offscreen_arrows = {}
game_over = False

editor_mode = False
editor_cam = None

cockpit_view = False  # Toggle between external & cockpit view

mouse_sensitivity = 28
mouse_pitch = 0
mouse_yaw = 0
max_look_angle = 25

# Initialize Ursina App
app = Ursina()
window.fullscreen = True
window.show_ursina_splash = True
window.borderless = True
window.vsync = True
window.color = color.rgb(0, 0, 0)
window.title = "Flight Simulator - Dogfight Mode"
mouse.locked = False
mouse.visible = True

def restart_game():
    os.execl(sys.executable, sys.executable, *sys.argv)


black_overlay = Entity(
    parent=camera.ui,
    model='quad',
    scale=(2, 2),
    color=color.black,
    z=-1
)


# HUD text
displayed = Text(
    "",
    parent=camera.ui,
    position=window.center - Vec2(0.5, 0),
    z=-2,
    origin=(-0.5, 0),
    scale=1.3,
    color=color.rgb(0, 255, 100)
)




def typewriter_text(text, base_delay=0.015):
    seq = Sequence()
    displayed.text = ""

    for char in text:
        seq.append(Func(lambda c=char: setattr(displayed, "text", displayed.text + c)))

        if char in ".!?":
            delay = base_delay * 10
        elif char in ",:;":
            delay = base_delay * 5
        elif char == "\n":
            delay = base_delay * 15
        else:
            delay = base_delay

        seq.append(Wait(delay + random.uniform(0, base_delay * 0.5)))

    return seq


def add_text(t):
    displayed.text += t
def clear_displayed():
    displayed.text = ""
def game_intro():
    global game_paused
    game_paused = True

    briefing_text = _build_mission_briefing_text(mission)
    displayed.text = ""

    Sequence(
        Wait(3),
        typewriter_text(briefing_text, base_delay=0.03),
        Wait(10),
        Func(start_game),  
        Wait(10),
        Func(clear_displayed),
        Func(lambda: black_overlay.animate_color(color.rgba(0,0,0,0), duration=2))

    ).start()

invoke(game_intro)
mission_start_time = time.time()
#Physics Constants
g = 9.81  # Gravity (m/s²)
vertical_velocity = 0  # Vertical velocity (m/s)
rho0 = 1.225  # Air density at sea level (kg/m³)
H = 8000  # Scale height for atmosphere (m)
S = 27.87  # Wing area of F-16 (m²)
Sf = 28  # Reference area for drag
mass = 12000  # Max takeoff weight (kg)
T_max = 129000  # Max thrust of F-16 (N)
Cd0 = 0.03  # Zero-lift drag coefficient
k = 0.07  # Induced drag factor
CL0 = 0.2  # Lift coefficient at zero AoA
CL_alpha = 0.12  # Lift curve slope per degree
missile_weight = 85  # Missile weight (kg)
missile_velocity = 300  # Missile speed (m/s)

# Combat Variables
player_health = 100
missile_count = 50
flare_count = 50
gun_ammo = 500
locked_target = None
target_index = 0
lock_progress = 0
lock_time_required = 2.0  # Seconds to achieve lock
is_locking = False
radar_range = 5000
lock_tone_playing = False
radar_enabled = True  # Toggle radar display

# Persistent progression tuning
upgrades = progression.get("upgrades", {})
radar_range += int(upgrades.get("radar_quality", 0)) * 400
missile_count += int(upgrades.get("missile_capacity", 0))
flare_count += int(upgrades.get("flare_capacity", 0))


def update_progression_on_win():
    global progression
    progression = load_json(PROGRESSION_FILE, default_progression())
    progression.setdefault("completed_nodes", [])
    progression.setdefault("node_stars", {})
    progression.setdefault("challenge_stars", {})
    progression.setdefault("unlocked_aircraft", ["f16", "f167"])
    progression.setdefault("selected_aircraft", "f167")
    progression.setdefault("upgrades", {})
    progression.setdefault("cosmetics", [])

    elapsed = time.time() - mission_start_time
    stars = 1
    if player_health >= 70:
        stars += 1
    bonus_time = mission.get("bonus_time")
    if bonus_time and elapsed <= bonus_time:
        stars += 1
    stars = min(stars, 3)

    if active_mission_type == "quest" and active_mission_id:
        if active_mission_id not in progression["completed_nodes"]:
            progression["completed_nodes"].append(active_mission_id)
        best = progression["node_stars"].get(active_mission_id, 0)
        progression["node_stars"][active_mission_id] = max(best, stars)
    elif active_mission_type == "challenge" and active_mission_id:
        best = progression["challenge_stars"].get(active_mission_id, 0)
        progression["challenge_stars"][active_mission_id] = max(best, stars)

    rewards = mission.get("rewards", {})
    for aircraft_id in rewards.get("aircraft_unlocks", []):
        if aircraft_id not in progression["unlocked_aircraft"]:
            progression["unlocked_aircraft"].append(aircraft_id)

    for key, value in rewards.get("upgrades", {}).items():
        progression["upgrades"][key] = progression["upgrades"].get(key, 0) + value

    for cosmetic in rewards.get("cosmetics", []):
        if cosmetic not in progression["cosmetics"]:
            progression["cosmetics"].append(cosmetic)

    progression["selected_aircraft"] = selected_aircraft_id
    save_json(PROGRESSION_FILE, progression)
# Load Textures & Sounds
runway_texture = load_texture('models/runway.jpg')
cockpit_texture = load_texture('models/cockpit.png')
grass_texture = load_texture('models/terraiin.jpg')
wmap = load_texture('models/no-zoom.jpeg')
plane_engine = Audio('models/plane_engine.mp3', loop=True, volume=0.1, autoplay=True)
crash_sound = Audio('models/crash.mp3', autoplay=False)
terrain_warning = Audio('models/terrain.mp3', autoplay=False)
explosion = Audio('models/explosion.mp3', autoplay=False)
#check for mp3 files ending in "music"
matched_files = []
    # Loop through files in the directory
suffix = "music.mp3"
for filename in os.listdir("models"):

    if filename.lower().endswith(suffix.lower()):
        matched_files.append(os.path.join("/models", filename))
x = len(matched_files)
bgm = Audio(random.choice(matched_files), autoplay=True, loop=True)

