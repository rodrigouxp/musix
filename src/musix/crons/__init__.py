import time
import schedule

from musix.utils.threading import background


@background
def start_cron_jobs(and_exit: bool = False):
    """
    This is the function that triggers the cron jobs.
    """
    from musix.lib.recipes.recents import RecentlyAdded, RecentlyPlayed
    from musix.lib.recipes.topstreamed import TopArtists

    # NOTE: RecentlyPlayed is not a CRON job, it's triggered here to
    # populate the values for the very first time.
    RecentlyPlayed()
    RecentlyAdded()

    register = not and_exit

    jobs = [
        TopArtists(register=register),
        TopArtists(duration="week", register=register),
    ]

    # Trigger all CRON jobs when the app is started.
    for job in jobs:
        job.run()

    # To manually trigger cron jobs, only once
    if and_exit:
        return

    # Run all CRON jobs on a loop.
    while True:
        schedule.run_pending()
        time.sleep(1)
