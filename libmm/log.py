import logging

from .config import global_settings


logging.basicConfig(
    filename=global_settings.log_file_path,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    filemode="w",
)
logger = logging.getLogger("libmm")


def print_and_log(msg, msg_type="info"):
    fn = getattr(logger, msg_type)
    fn(msg)
    print(msg)


class LoggedException(Exception):
    ERROR_TYPE = "error"

    def __init__(self, message):
        self.message = message
        # print_and_log(self.message, msg_type=LoggedException.ERROR_TYPE)
        getattr(logger, LoggedException.ERROR_TYPE)(self.message)
        super().__init__(self.message)
