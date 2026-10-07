from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld

from .options import option_groups


class ValorantWebWorld(WebWorld):
    game = "Valorant"
    theme = "stone"

    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "How to set up the VALORANT client (and the optional companion app) for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["jonas"],
        )
    ]

    option_groups = option_groups
