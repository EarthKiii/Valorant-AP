from worlds.LauncherComponents import Component, Type, components

try:
    from worlds.LauncherComponents import launch
except ImportError:  # Archipelago < 0.6.7
    from worlds.LauncherComponents import launch_subprocess as launch


def run_client(*args: str) -> None:
    from .client.launch import launch_valorant_client

    launch(launch_valorant_client, name="Valorant Client", args=args)


components.append(
    Component(
        "Valorant Client",
        func=run_client,
        game_name="Valorant",
        component_type=Type.CLIENT,
        supports_uri=True,
        description="Tracks your VALORANT matches and sends checks.",
    )
)
