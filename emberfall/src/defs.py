"""EMBERFALL — static game data. All gameplay numbers live here."""
from __future__ import annotations

TILE_W, TILE_H, ELEV = 64, 32, 13
MAP_W = MAP_H = 84
FPS = 60
SIM_HZ = 30
SCREEN_W, SCREEN_H = 1600, 900

NEUTRAL, PLAYER, ENEMY = 0, 1, 2

PALETTE = dict(
    ember="#ff8a3d", gold="#d9a441", crimson="#a83a3a", steel="#cfd6df",
    moss="#4b6b3f", slate="#6d6a63", bone="#d8d2bd", violet="#5a4470",
    ink="#161018", parchment="#e8dcc0", teal="#2f6b6b", blood="#5c1f28",
)

TEAM_COLORS = {
    PLAYER: dict(main="#c8452f", light="#ff8a3d", dark="#5d1d16", ui="#e8b25a"),
    ENEMY: dict(main="#6b4a86", light="#b58ad2", dark="#2c1c3d", ui="#a37bd6"),
    NEUTRAL: dict(main="#7a6a45", light="#c9b784", dark="#332d1f", ui="#c9b784"),
}

DMG_MULT = {
    "normal": dict(none=1.0, light=1.2, medium=1.0, heavy=0.9, fortified=0.55),
    "pierce": dict(none=1.0, light=1.35, medium=1.0, heavy=0.7, fortified=0.45),
    "siege": dict(none=1.0, light=0.85, medium=0.95, heavy=1.0, fortified=1.65),
    "magic": dict(none=1.0, light=1.1, medium=1.0, heavy=1.2, fortified=0.6),
    "holy": dict(none=1.0, light=1.1, medium=1.05, heavy=1.0, fortified=0.7),
}


def damage_mult(kind: str, armor_type: str) -> float:
    return DMG_MULT.get(kind, {}).get(armor_type, 1.0)


PROJECTILES = {
    "arrow": dict(speed=15, arc=18, color=(232, 220, 192), trail=0.22, size=2.2),
    "bolt": dict(speed=17, arc=10, color=(184, 224, 216), trail=0.3, size=2.6),
    "frost": dict(speed=12, arc=26, color=(159, 231, 255), trail=0.5, size=3.4),
    "shadow": dict(speed=11, arc=22, color=(180, 135, 232), trail=0.55, size=3.2),
    "siege": dict(speed=9, arc=60, color=(215, 195, 154), trail=0.35, size=4.5),
    "holy": dict(speed=18, arc=6, color=(255, 230, 166), trail=0.4, size=3),
}


def _unit(**o):
    base = dict(radius=0.34, sight=8, armor_type="medium", damage_type="normal",
                projectile=None, food=1, bounty=10, xp=25, hero=False, worker=False,
                ranged=False, mana=0, summon=False)
    base.update(o)
    return base


UNITS = {
    "worker": _unit(
        id="worker", name="Ember Worker", icon="worker", rig="worker",
        hp=220, armor=0, armor_type="light", damage_type="normal",
        dmg=(6, 9), range=1.05, cooldown=1.4, speed=2.75, sight=7,
        food=1, cost=dict(g=75), build_time=14, bounty=6, xp=12,
        worker=True, radius=0.3,
        desc="Delves the mines, fells the vale and raises your halls. Can build and repair."),
    "footman": _unit(
        id="footman", name="Ember Footman", icon="footman", rig="footman",
        hp=420, armor=2, armor_type="heavy", damage_type="normal",
        dmg=(12, 15), range=1.15, cooldown=1.35, speed=2.3, sight=8,
        food=2, cost=dict(g=135), build_time=20, bounty=14, xp=34, radius=0.35,
        desc="Shield-wall infantry. Cheap, stubborn, and the backbone of the Emberhold line."),
    "archer": _unit(
        id="archer", name="Vale Archer", icon="archer", rig="archer",
        hp=285, armor=0, armor_type="light", damage_type="pierce",
        dmg=(13, 16), range=5.5, cooldown=1.6, speed=2.45, sight=9,
        food=2, cost=dict(g=130, l=20), build_time=20, projectile="arrow",
        bounty=14, xp=34, radius=0.32, ranged=True,
        desc="Longbow skirmisher. Shreds light troops; keep her behind steel."),
    "knight": _unit(
        id="knight", name="Ember Knight", icon="knight", rig="knight",
        hp=700, armor=4, armor_type="heavy", damage_type="normal",
        dmg=(24, 30), range=1.3, cooldown=1.5, speed=3.0, sight=9,
        food=3, cost=dict(g=245, l=60), build_time=30, bounty=26, xp=62,
        radius=0.46, requires="keep",
        desc="Mounted hammer of the Emberhold. Breaks lines and hunts siege."),
    "priest": _unit(
        id="priest", name="Kindled Priest", icon="priest", rig="priest",
        hp=270, armor=0, armor_type="light", damage_type="holy",
        dmg=(9, 12), range=4.5, cooldown=1.9, speed=2.35, sight=9,
        food=2, cost=dict(g=145, l=40), build_time=26, projectile="holy",
        bounty=16, xp=40, heal=14, ranged=True,
        desc="Mends the wounded with consecrated flame. Fragile — guard him."),
    "ballista": _unit(
        id="ballista", name="Ember Ballista", icon="ballista", rig="ballista",
        hp=380, armor=2, armor_type="heavy", damage_type="siege",
        dmg=(44, 52), range=8, cooldown=3.0, speed=1.55, sight=10,
        food=3, cost=dict(g=180, l=80), build_time=32, projectile="siege",
        bounty=24, xp=60, radius=0.5, requires="keep", ranged=True,
        desc="Siege engine. Grinds fortifications to splinters, helpless in a brawl."),
    "ghoul": _unit(
        id="ghoul", name="Ghoul", icon="ghoul", rig="ghoul",
        hp=350, armor=1, armor_type="light", damage_type="normal",
        dmg=(12, 15), range=1.1, cooldown=1.15, speed=3.0, sight=8,
        food=1, cost=dict(g=110), build_time=16, bounty=12, xp=30, enemy=True,
        desc="A hungry corpse with claws. Fast, cheap, endless."),
    "fiend": _unit(
        id="fiend", name="Crypt Fiend", icon="fiend", rig="fiend",
        hp=410, armor=2, armor_type="medium", damage_type="pierce",
        dmg=(17, 21), range=5.5, cooldown=1.8, speed=2.2, sight=9,
        projectile="bolt", bounty=18, xp=46, radius=0.4, ranged=True, enemy=True,
        desc="Spider-kin that spits bone shards from the dark."),
    "necromancer": _unit(
        id="necromancer", name="Necromancer", icon="necromancer", rig="necromancer",
        hp=285, armor=0, armor_type="light", damage_type="magic",
        dmg=(9, 12), range=5, cooldown=2.0, speed=2.2, sight=9,
        projectile="shadow", bounty=22, xp=58, enemy=True, summoner=True, ranged=True,
        desc="Raises skeletons from the fallen. Kill him first."),
    "abomination": _unit(
        id="abomination", name="Abomination", icon="abomination", rig="abomination",
        hp=1000, armor=4, armor_type="heavy", damage_type="normal",
        dmg=(30, 38), range=1.45, cooldown=1.9, speed=2.0, sight=8,
        food=4, cost=dict(g=260), build_time=34, bounty=42, xp=95, radius=0.6, enemy=True,
        desc="A hill of stitched meat. Slow, terrible, very hard to put down."),
    "revenant": _unit(
        id="revenant", name="Frost Revenant", icon="revenant", rig="revenant",
        hp=480, armor=1, armor_type="light", damage_type="magic",
        dmg=(22, 28), range=6, cooldown=2.1, speed=2.0, sight=10,
        projectile="frost", bounty=32, xp=72, radius=0.38, enemy=True, slow_hit=0.35, ranged=True,
        desc="A wailing shade of old winter. Its touch numbs the limbs."),
    "skeleton": _unit(
        id="skeleton", name="Skeleton", icon="skeleton", rig="skeleton",
        hp=130, armor=0, armor_type="none", damage_type="normal",
        dmg=(6, 9), range=1.05, cooldown=1.3, speed=2.6, sight=7,
        food=0, bounty=2, xp=8, enemy=True, summon=True, duration=28,
        desc="A puppet of bone, dragged briefly back to war."),
    "goblin": _unit(
        id="goblin", name="Vale Goblin", icon="goblin", rig="goblin",
        hp=260, armor=1, armor_type="light", damage_type="normal",
        dmg=(11, 14), range=1.1, cooldown=1.3, speed=3.2, sight=8,
        food=0, bounty=16, xp=28, radius=0.4, neutral=True,
        desc="A lean scavenger of the high grass. Guards the old mines."),
    "goblin-brute": _unit(
        id="goblin-brute", name="Goblin Brute", icon="goblin-brute", rig="goblin-brute", scale=1.2,
        hp=700, armor=2, armor_type="medium", damage_type="normal",
        dmg=(22, 28), range=1.3, cooldown=1.6, speed=3.0, sight=9,
        food=0, bounty=90, xp=120, radius=0.55, neutral=True,
        desc="The warband leader. His bounty is worth a small fortune."),
    "hollow-king": _unit(
        id="hollow-king", name="The Hollow King", icon="hollow-king", rig="hollow-king",
        hp=5200, armor=6, armor_type="heavy", damage_type="normal",
        dmg=(52, 66), range=1.7, cooldown=2.1, speed=1.9, sight=12,
        food=0, bounty=500, xp=1200, radius=0.8, enemy=True, boss=True,
        desc="The crownless thing that wears the vale like a grave. It will not kneel."),
    "hero": _unit(
        id="hero", name="Marshal Aldric", icon="hero", rig="hero",
        hp=800, mana=220, armor=3, armor_type="heavy", damage_type="normal",
        dmg=(26, 32), range=1.4, cooldown=1.45, speed=2.6, sight=10,
        food=0, bounty=0, xp=0, radius=0.42, hero=True,
        desc="Last Ember of the Emberhold. Every wound the Host takes feeds his fire."),
}

HERO_LEVELS = [0, 120, 300, 540, 840, 1200, 1640, 2160, 2780, 3500]
HERO_GROWTH = dict(hp=72, mana=22, dmg=3.2, armor=0.35)

ABILITIES = {
    "ember-lance": dict(
        id="ember-lance", name="Ember Lance", icon="ember-lance", hotkey="Q",
        mana=60, cooldown=9, range=7, target="unit", unlock=1,
        desc="Hurl a spear of living fire. Heavy damage and a brief stun.",
        dmg=lambda lv: 70 + 22 * lv, stun=1.2),
    "aegis": dict(
        id="aegis", name="Aegis of Embers", icon="aegis", hotkey="W",
        mana=50, cooldown=16, range=0, target="self", unlock=2,
        desc="Wrap yourself in a shield of cinders that absorbs damage for 8 seconds.",
        shield=lambda lv: 110 + 55 * lv, duration=8),
    "consecrate": dict(
        id="consecrate", name="Consecrate", icon="consecrate", hotkey="E",
        mana=70, cooldown=12, range=6, target="ground", radius=3.6, unlock=4,
        desc="Scorch the ground. Burns enemies and heals every ally standing in the fire.",
        dmg=lambda lv: 55 + 18 * lv, heal=lambda lv: 45 + 12 * lv),
    "daybreak": dict(
        id="daybreak", name="Daybreak", icon="daybreak", hotkey="R",
        mana=140, cooldown=90, range=8, target="ground", radius=5, unlock=6,
        desc="The last dawn of the Emberhold. A pillar of light stuns and burns everything near it.",
        dmg=lambda lv: 220 + 60 * lv, stun=2.0),
}


def _building(**o):
    base = dict(armor=3, armor_type="fortified", sight=7, builds_units=False,
                size=(3, 3), height=60, food=0, enemy=False)
    base.update(o)
    return base


BUILDINGS = {
    "townhall": _building(
        id="townhall", name="Emberhold Hall", icon="townhall", rig="townhall",
        hp=1800, armor=4, size=(4, 4), cost=dict(g=380, l=200), build_time=55,
        food=10, dropoff=True, trains=["worker"], sight=10, height=92, upgrade="keep",
        desc="Seat of the Emberhold. Trains workers, stores gold and lumber."),
    "keep": _building(
        id="keep", name="Emberhold Keep", icon="keep", rig="keep",
        hp=2600, armor=5, size=(4, 4), cost=dict(g=300, l=180), build_time=60,
        food=12, dropoff=True, trains=["worker"], sight=11, height=108, requires="townhall",
        desc="A greater hall of stone and fire. Unlocks knights and ballistae."),
    "farm": _building(
        id="farm", name="Sunfield Farm", icon="farm", rig="farm",
        hp=480, armor=2, size=(2, 2), cost=dict(g=80), build_time=15,
        food=6, sight=5, height=34,
        desc="Feeds the host. Each farm supports six more soldiers."),
    "barracks": _building(
        id="barracks", name="Barracks", icon="barracks", rig="barracks",
        hp=1050, armor=3, size=(3, 3), cost=dict(g=140, l=60), build_time=26,
        trains=["footman", "archer"], builds_units=True, sight=7, height=64,
        desc="Trains footmen and archers. The yard never empties."),
    "mill": _building(
        id="mill", name="Lumber Mill", icon="mill", rig="mill",
        hp=800, armor=2, size=(3, 3), cost=dict(g=120), build_time=22,
        sight=7, height=62, desc="Sharpens axes and stores timber. Required for a Blacksmith."),
    "blacksmith": _building(
        id="blacksmith", name="Blacksmith", icon="blacksmith", rig="blacksmith",
        hp=900, armor=3, size=(3, 3), cost=dict(g=140, l=50), build_time=26,
        sight=6, height=58, research=["weapons1", "weapons2", "armor1", "armor2"],
        requires="mill", desc="Forge and anvil. Sharpens blades and hardens plate."),
    "sanctum": _building(
        id="sanctum", name="Arcane Sanctum", icon="sanctum", rig="sanctum",
        hp=820, armor=2, size=(3, 3), cost=dict(g=150, l=100), build_time=30,
        sight=8, height=74, trains=["priest"], requires="barracks",
        desc="Where ember-priests keep the old rites. Trains priests."),
    "tower": _building(
        id="tower", name="Guard Tower", icon="tower", rig="tower",
        hp=780, armor=4, size=(2, 2), cost=dict(g=110, l=70), build_time=20,
        sight=10, height=80,
        attack=dict(dmg=(19, 24), range=7.5, cooldown=1.5, type="pierce", projectile="arrow"),
        desc="A stone watchtower. Long reach, steady damage, no legs to run."),
    "altar": _building(
        id="altar", name="Altar of Embers", icon="altar", rig="altar",
        hp=640, armor=2, size=(2, 2), cost=dict(g=180, l=40), build_time=20,
        sight=6, height=56, desc="The Marshal revives here. Do not let it fall."),
    "necropolis": _building(
        id="necropolis", name="Necropolis", icon="necropolis", rig="necropolis",
        hp=5200, armor=6, size=(5, 5), sight=12, height=120, food=20, enemy=True,
        desc="The Hollow Crown's seat. Break it and the vale is free."),
    "ziggurat": _building(
        id="ziggurat", name="Ziggurat", icon="ziggurat", rig="ziggurat",
        hp=950, armor=4, size=(2, 2), sight=8, height=72, food=8, enemy=True,
        desc="A spire of bone that feeds the Host."),
    "crypt": _building(
        id="crypt", name="Crypt", icon="crypt", rig="crypt",
        hp=1200, armor=4, size=(3, 3), sight=7, height=58, enemy=True,
        desc="Ghouls crawl out of the wet dark here."),
    "slaughterhouse": _building(
        id="slaughterhouse", name="Slaughterhouse", icon="slaughterhouse", rig="slaughterhouse",
        hp=1350, armor=4, size=(3, 3), sight=6, height=66, enemy=True,
        desc="Where the Host stitches its abominations."),
    "temple": _building(
        id="temple", name="Temple of the Damned", icon="temple", rig="temple",
        hp=1050, armor=3, size=(3, 3), sight=8, height=82, enemy=True,
        desc="Necromancers whisper to things that should sleep."),
    "bonetower": _building(
        id="bonetower", name="Bone Tower", icon="bonetower", rig="bonetower",
        hp=820, armor=4, size=(2, 2), sight=10, height=86, enemy=True,
        attack=dict(dmg=(24, 30), range=8, cooldown=1.7, type="magic", projectile="frost"),
        desc="A spire that spits frost at the living."),
    "altarhollow": _building(
        id="altarhollow", name="Altar of the Hollow", icon="altarhollow", rig="altarhollow",
        hp=900, armor=3, size=(3, 3), sight=7, height=64, enemy=True,
        desc="The King's throne of bone."),
}

UPGRADES = {
    "weapons1": dict(
        id="weapons1", name="Iron Weapons", icon="weapons", hotkey="Q",
        cost=dict(g=100, l=100), time=30,
        desc="Emberhold blades bite deeper. +3 attack damage to all soldiers.",
        apply="dmg", amount=3),
    "weapons2": dict(
        id="weapons2", name="Ember Steel", icon="weapons", hotkey="W",
        cost=dict(g=190, l=180), time=40, req_upgrade="weapons1",
        desc="Fold fire into the steel. +3 more attack damage.",
        apply="dmg", amount=3),
    "armor1": dict(
        id="armor1", name="Steel Plate", icon="armor", hotkey="A",
        cost=dict(g=100, l=100), time=30,
        desc="Reinforced plate for the line. +3 armor.",
        apply="armor", amount=3),
    "armor2": dict(
        id="armor2", name="Kingsguard Plate", icon="armor", hotkey="S",
        cost=dict(g=190, l=180), time=40, req_upgrade="armor1",
        desc="The old kings' smithwork. +3 more armor.",
        apply="armor", amount=3),
}

BUILD_MENU = ["farm", "barracks", "mill", "blacksmith", "sanctum", "tower", "altar", "keep"]
PLAYER_TRAIN = {
    "townhall": ["worker"], "keep": ["worker"],
    "barracks": ["footman", "archer", "knight"],
    "sanctum": ["priest"],
}
ENEMY_TRAIN = {"crypt": ["ghoul", "fiend"], "slaughterhouse": ["abomination"],
               "temple": ["necromancer", "revenant"]}

FACTION = {
    PLAYER: dict(name="Emberhold", color="#c8452f", accent="#ff8a3d",
                 motto="The last embers answer."),
    ENEMY: dict(name="Hollow Host", color="#6b4a86", accent="#b58ad2",
                motto="The crown remembers every grave."),
}

DIFFICULTY = {
    "squire": dict(id="squire", name="Squire", income=0.75, hp=0.82, dmg=0.85,
                   wave_gap=1.25, wave_size=0.75, speed=0.95,
                   blurb="The Host is slow to wake. For learning the vale."),
    "knight": dict(id="knight", name="Knight", income=1.0, hp=1.0, dmg=1.0,
                   wave_gap=1.0, wave_size=1.0, speed=1.0,
                   blurb="A war worth fighting. The intended balance."),
    "warlord": dict(id="warlord", name="Warlord", income=1.3, hp=1.18, dmg=1.12,
                    wave_gap=0.82, wave_size=1.25, speed=1.05,
                    blurb="The vale drowns. Only a hard, fast game survives."),
}

OBJECTIVE_MAIN = "Destroy the Necropolis and end the Hollow King."
OBJECTIVE_BONUS = "Break the wolf-packs at the old mines for coin."
