from musix.config import UserConfig
from musix.models.user import User
from musix.utils import classproperty


class GeneralStore:
    """
    This store can be used to track various states
    """

    admin_exists: bool = False
    root_dirs_set: bool = False
    scan_message: str = ""
    full_scan_in_progress: bool = False

    @classproperty
    def onboarding_complete(cls):
        return cls.admin_exists and cls.root_dirs_set

    @classmethod
    def load_onboarding_data(cls, users: list[User]):
        # INFO: Check if there are any users in the db
        if not users:
            cls.admin_exists = False

        for user in users:
            if "admin" in user.roles:
                cls.admin_exists = True
                break

        if UserConfig().rootDirs:
            cls.root_dirs_set = True

    @classmethod
    def start_full_scan(cls):
        """
        Starts a full scan.
        """
        cls.full_scan_in_progress = True
        cls.scan_message = "Full scan in progress... This may take a while."

    @classmethod
    def end_full_scan(cls):
        """
        Ends a full scan.
        """
        cls.full_scan_in_progress = False
        cls.scan_message = ""