from test.bases import WorldTestBase

from ..world import ValorantWorld


class ValorantTestBase(WorldTestBase):
    game = "Valorant"
    world: ValorantWorld
