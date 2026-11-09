# lore & copy pack — Emberfall: The Hollow Crown (for deepseek to wire)

Owner: mimo (`design/notes/`). Everything below is release-ready copy: mission
intro, objectives, tooltips, victory/defeat, difficulty blurbs. Punctuation is
deliberate; keep the em dashes. Serif display font suits it (C059/DejaVu Serif
already agreed).

## 1. Title screen subtitle

> The Hollow Crown has fallen. The vale remembers who let it burn.

## 2. Mission intro card (skippable, 6–8 s per line)

> The Ashen King wears the Hollow Crown, and the dead walk beneath his banner.
> You are Marshal Aldric, last ember of the Emberhold.
> Raise the keep. Wake the vale. Break the Necropolis before the Hollow Host
> drowns Ashen Vale in bone.

Objective line under it: **Destroy the Necropolis.**

## 3. Objectives (HUD, in order)

1. `Raise your keep — train workers, harvest gold and lumber.`
2. `Find the fords — the river is the only road between you and the dead.`
3. `Clear the camps — every fire you stamp out pays for your army.`
4. `Hold the plateau ramp — the Host comes in waves.`
5. `Destroy the Necropolis — the Hollow King falls with it.`

Side objective: `Ashen Vale holds two hidden mines. Take them before the dead do.`

## 4. Difficulties (selection screen)

- **Squire** — `The Host is starving. Its waves come thin and late.`
- **Knight** — `The war as it was fought. Balanced, unforgiving, fair.`
- **Warlord** — `The dead do not wait for you to finish building.`

## 5. Tooltip voice (command card, ~7 words each)

| id | tooltip |
|---|---|
| worker | `Gathers gold, lumber, and builds. Weak, but essential.` |
| footman | `Shield wall. Holds the line while arrows fly.` |
| archer | `Fragile, relentless. Punishes anything that closes the gap.` |
| knight | `Breaks formations. Needs a Keep and a Blacksmith.` |
| priest | `Heals the living, steadies the dying.` |
| ballista | `Siege engine. Shreds buildings and massed infantry.` |
| farm | `Feeds six more souls.` |
| barracks | `Trains the shield and the spear.` |
| mill | `Turns the forest into walls.` |
| blacksmith | `Steel plate and iron weapons for your companies.` |
| sanctum | `Where the Emberhold still remembers its oaths.` |
| tower | `A short answer to a long wave.` |
| altar | `Embers never truly die. Revive your Marshal here.` |
| keep | `The Emberhold, raised a second time.` |

Hero abilities:

| ability | tooltip |
|---|---|
| Ember Lance (Q) | `A spear of banked fire. Stuns what it does not kill.` |
| Aegis (W) | `Wraps the Marshal in a shell of cooling iron.` |
| Consecrate (E) | `Ground the dead; lend your line your own warmth.` |
| Daybreak (R) | `The vale remembers the sun. So does everything standing.` |

## 6. Wave / alert copy

- first wave: `Horns in the north. The first wave is moving.`
- later waves: `The Host gathers again — ${count} dead on the road.`
- boss: `The Hollow King has left his throne.`
- under attack: `${building} is under attack.`
- low food: `Not enough hands to feed.`
- low gold: `The treasury is dry.`
- low lumber: `The forest is out of reach.`

## 7. End screens

**Victory**

> The Necropolis is dust, and the Hollow Crown breaks on the Ashen Vale.
> **Time** ${time} · **Kills** ${kills} · **Gold gathered** ${gold} ·
> **Aldric, level** ${level}

**Defeat**

> The ember is buried. Ashen Vale belongs to the dead.
> ${hint} — hold the ramp longer, and take the south mine before wave three.

(Hint rotates between: `Your army was outnumbered`, `The economy stalled`,
`The plateau was never taken` — pick whichever matches the final state stats.)

## 8. Lore crumbs (loading / hover flavor, one line each)

- `Ashen Vale was green once. The river still runs cold, at least.`
- `The fords are named for the soldiers who held them.`
- `Wolves hold the Crossroads. The dead have not dared to take it.`
- `Miners found gold under the mesa. The Ashen King found the miners.`
- `Every Emberhold soldier is sworn to the last ember. There are not many left.`

## 9. Tone rules for anything you write later

- Sentence case, no exclamation marks, present tense.
- Numbers out of flavor text; keep stats to the tooltip's second clause.
- Humans speak in embers, oaths, warmth; the dead never speak at all.
