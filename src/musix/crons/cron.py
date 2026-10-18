import schedule


from abc import ABC, abstractmethod


class CronJob(ABC):
    """
    A cron job that will be run on a regular interval.
    """

    name: str
    hours: int = 1

    def __init__(self, register: bool = True):
        """
        Pass register=False to create a job for a one-shot `run()` call
        without adding it to the shared `schedule` registry.
        """
        if register:
            schedule.every(self.hours).hours.do(self.run)

    @abstractmethod
    def run(self):
        """
        The function that will be called by the cron job.
        """
        ...
