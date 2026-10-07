import asyncio
from collections.abc import Sequence


async def main(args) -> None:
    from CommonClient import server_loop
    from Utils import gui_enabled

    from .context import ValorantContext

    ctx = ValorantContext(args.connect, args.password, companion_port=args.companion_port)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()
    ctx.start_valorant_tasks()

    await ctx.exit_event.wait()
    await ctx.shutdown()


def launch_valorant_client(*args: Sequence[str]) -> None:
    import colorama
    import Utils
    from CommonClient import get_base_parser, handle_url_arg

    from .context import DEFAULT_COMPANION_PORT

    parser = get_base_parser(description="Archipelago client for VALORANT.")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--companion-port", "--bridge-port", dest="companion_port", type=int,
                        default=DEFAULT_COMPANION_PORT, help="Local port the companion app connects to.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    launch_args = handle_url_arg(parser.parse_args(args), parser)

    Utils.init_logging("ValorantClient", exception_logger="Client")
    colorama.just_fix_windows_console()
    asyncio.run(main(launch_args))
    colorama.deinit()
