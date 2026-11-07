"""The A12 evaluation set: frames with known content, and questions with known answers.

Frames (24):
- 9 signs drawn in code (English, French, Arabic; one of them very dark, for A4),
  so their true text is known exactly and they are identical on every machine;
- 15 real photos: 6 from COCO val2017 (the standard detection benchmark), 2 that ship
  with ultralytics, and 7 freely licensed photos of stairs and doors from Wikimedia
  Commons. They download once into data/test_images (git-ignored).
Questions (44): 12-19 per language, each with the set of frames that answer it, plus
"unanswerable" questions (nothing relevant was seen) to test the 0.25 threshold.

Limits, said honestly: 24 frames is small and the signs are synthetic. The same
script runs on a real recorded walk (run_eval.py --video), which is the real test.
"""

import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

COCO = "http://images.cocodataset.org/val2017/{}.jpg"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width=640"


@dataclass
class Item:
    id: str
    load: Callable[[], np.ndarray]
    text: str = ""  # exact text on a sign ("" for photos): OCR ground truth
    hazard: str | None = None  # "stairs" | "closed_door" | None: warning ground truth
    source: str = ""


@dataclass
class Query:
    text: str
    language: str  # en | fr | ar
    relevant: frozenset[str]  # item ids that answer it; empty = unanswerable


def _cached(name: str, url: str) -> np.ndarray:
    path = settings.models_path.parent / "test_images" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "voice-assistant-eval/1.0"})
        for attempt in range(3):  # slow connections time out now and then
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    data = response.read()
                break
            except OSError:
                if attempt == 2:
                    raise
        partial = path.with_suffix(".part")  # never leave half a photo behind
        partial.write_bytes(data)
        partial.replace(path)
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"{path} is not a readable image (delete it and run again)")
    return image


def coco(image_id: str) -> Callable[[], np.ndarray]:
    return lambda: _cached(f"coco_{image_id}.jpg", COCO.format(image_id))


def commons(name: str) -> Callable[[], np.ndarray]:
    return lambda: _cached(f"commons_{name}", COMMONS.format(urllib.parse.quote(name)))


def asset(name: str) -> Callable[[], np.ndarray]:
    def load() -> np.ndarray:
        import ultralytics

        return cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / name))
    return load


def drawn_sign(lines: list[str], background=(30, 120, 40), color=(255, 255, 255),
               dark: bool = False) -> Callable[[], np.ndarray]:
    def load() -> np.ndarray:
        from tests.vision import signs

        image = signs.sign(lines, background=background, color=color)
        if dark:  # a corridor at night: 8% of the light, same sensor noise (A4)
            noisy = image * 0.08 + np.random.default_rng(5).normal(0, 4, image.shape)
            image = np.clip(np.round(noisy), 0, 255).astype(np.uint8)
        return image
    return load


ITEMS: list[Item] = [
    # ---- signs (drawn) ----
    Item("exit_en", drawn_sign(["EXIT", "Room 204"]), "EXIT Room 204", source="drawn"),
    Item("exit_en_dark", drawn_sign(["EXIT", "Room 204"], dark=True), "EXIT Room 204",
         source="drawn, 8% light"),
    Item("sortie_fr", drawn_sign(["Sortie", "Escalier"], (20, 60, 140)), "Sortie Escalier",
         source="drawn"),
    Item("exit_ar", drawn_sign(["مخرج", "الطابق الأول"], (150, 30, 30)), "مخرج الطابق الأول",
         source="drawn"),
    Item("pharmacy", drawn_sign(["PHARMACIE", "صيدلية"], (0, 130, 70)), "PHARMACIE صيدلية",
         source="drawn"),
    Item("elevator", drawn_sign(["ASCENSEUR", "مصعد"], (60, 70, 90)), "ASCENSEUR مصعد",
         source="drawn"),
    Item("toilets", drawn_sign(["TOILETTES", "WC"], (235, 235, 235), (20, 20, 20)), "TOILETTES WC",
         source="drawn"),
    Item("room105", drawn_sign(["Salle 105", "Dr. Haddad"], (90, 50, 20)), "Salle 105 Dr. Haddad",
         source="drawn"),
    Item("cafeteria", drawn_sign(["Cafeteria", "8:00 - 16:00"], (160, 90, 0)),
         "Cafeteria 8:00 - 16:00", source="drawn"),
    # ---- real photos ----
    Item("living_room", coco("000000000139"), source="COCO val2017 #139"),
    Item("bedroom", coco("000000000632"), source="COCO val2017 #632"),
    Item("kitchen", coco("000000000802"), source="COCO val2017 #802"),
    Item("stop_sign", coco("000000000724"), "STOP", source="COCO val2017 #724 (upside down)"),
    Item("kids_tennis", coco("000000001000"), source="COCO val2017 #1000"),
    Item("skier", coco("000000000785"), source="COCO val2017 #785"),
    Item("street_bus", asset("bus.jpg"), source="ultralytics bus.jpg"),
    Item("two_men", asset("zidane.jpg"), source="ultralytics zidane.jpg"),
    Item("stairs_down", commons("A_staircase_to_first_floor.jpg"), hazard="stairs",
         source="Wikimedia Commons"),
    Item("stairs_spiral", commons("Internal_staircase.jpg"), hazard="stairs",
         source="Wikimedia Commons"),
    Item("stairs_up", commons("Staircase_1.jpg"), hazard="stairs", source="Wikimedia Commons"),
    Item("stairs_metal", commons("Stairs-6304.jpg"), hazard="stairs", source="Wikimedia Commons"),
    Item("door_blue", commons("Interior_door_19-10-12_056.jpg"), hazard="closed_door",
         source="Wikimedia Commons"),
    Item("door_padlock", commons("Closed_door_02.jpg"), hazard="closed_door",
         source="Wikimedia Commons"),
    Item("door_carved", commons("Wooden_door,_Murnau,_Bavaria,_Germany.jpg"),
         hazard="closed_door", source="Wikimedia Commons"),
]

EXITS = frozenset({"exit_en", "exit_en_dark", "sortie_fr", "exit_ar"})
STAIRS = frozenset({"stairs_down", "stairs_spiral", "stairs_up", "stairs_metal", "sortie_fr"})
DOORS = frozenset({"door_blue", "door_padlock", "door_carved"})
NONE: frozenset[str] = frozenset()


def _q(text: str, language: str, *relevant) -> Query:
    ids: set[str] = set()
    for r in relevant:
        ids |= set(r) if isinstance(r, frozenset) else {r}
    return Query(text, language, frozenset(ids))


QUERIES: list[Query] = [
    # ---- English ----
    _q("What did the exit sign say?", "en", EXITS),
    _q("Room 204", "en", "exit_en", "exit_en_dark"),
    _q("Where is the pharmacy?", "en", "pharmacy"),
    _q("elevator", "en", "elevator"),
    _q("toilets", "en", "toilets"),
    _q("Dr. Haddad's office", "en", "room105"),
    _q("When does the cafeteria open?", "en", "cafeteria"),
    _q("stairs", "en", STAIRS),
    _q("a closed door", "en", DOORS),
    _q("a living room with a TV", "en", "living_room"),
    _q("a bedroom with a bookshelf", "en", "bedroom"),
    _q("a kitchen with a refrigerator", "en", "kitchen"),
    _q("a stop sign", "en", "stop_sign"),
    _q("a bus in the street", "en", "street_bus"),
    _q("children playing tennis", "en", "kids_tennis"),
    _q("someone skiing", "en", "skier"),
    _q("a plate of spaghetti", "en", NONE),
    _q("a dog on the beach", "en", NONE),
    _q("a swimming pool", "en", NONE),
    # ---- French ----
    _q("Qu'est-ce qui était écrit sur le panneau de sortie ?", "fr", EXITS),
    _q("pharmacie", "fr", "pharmacy"),
    _q("Où est l'ascenseur ?", "fr", "elevator"),
    _q("les toilettes", "fr", "toilets"),
    _q("salle 105", "fr", "room105"),
    _q("Où est l'escalier ?", "fr", STAIRS),
    _q("une porte fermée", "fr", DOORS),
    _q("un salon avec une télévision", "fr", "living_room"),
    _q("une cuisine", "fr", "kitchen"),
    _q("un bus dans la rue", "fr", "street_bus"),
    _q("quelqu'un qui fait du ski", "fr", "skier"),
    _q("un chat sur le canapé", "fr", NONE),
    _q("une voiture rouge", "fr", NONE),
    # ---- Arabic ----
    _q("شو مكتوب على لافتة المخرج؟", "ar", EXITS),
    _q("الطابق الأول", "ar", "exit_ar"),
    _q("صيدلية", "ar", "pharmacy"),
    _q("وين المصعد؟", "ar", "elevator"),
    _q("درج", "ar", STAIRS),
    _q("باب مغلق", "ar", DOORS),
    _q("غرفة جلوس فيها تلفاز", "ar", "living_room"),
    _q("مطبخ", "ar", "kitchen"),
    _q("حافلة في الشارع", "ar", "street_bus"),
    _q("أطفال يلعبون التنس", "ar", "kids_tennis"),
    _q("طائرة في السماء", "ar", NONE),
    _q("قطة", "ar", NONE),
]
