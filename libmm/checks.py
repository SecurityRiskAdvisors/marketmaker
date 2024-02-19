from abc import ABC, abstractmethod

from .sql import session, Variant
from .type import List, Tuple
from .log import logger
from .mitre import get_valid_tactic_ids_for_tid
from .utils import resolve_str_or_path
from .config import global_settings


# TODO: implement as extension and rewrite

MESSAGE_DELIMETER = " | "


class Check(ABC):
    """
    Checks are runtime validation logic for objects such as Variants and Blueprints.
    Developers should implement checks using a two-tiered hierarchy.
    The first tier should cover the object being checked (e.g. Variant) and implement the main() function.
    The second tier should implement one specific check for that object and implement the check() function.

    Note: the run() function should be left as-is
    """

    @staticmethod
    @abstractmethod
    def check(*args, **kwargs):
        """
        Function to implement the main logic of the check.
        This should be implemented by grandchild classes
        """
        pass

    @classmethod
    @abstractmethod
    def main(cls, *args, **kwargs) -> bool:
        """
        Function to implement the handling of the check's results after calling it.
        This should be implemented by intermediary classes
        """
        pass

    @classmethod
    def run(cls, *args, **kwargs):
        """
        Function to be called when executing check.
        This function handles conventions for checks and should not be overriden.
        Implement check handling login in main() and check logic in check()
        """
        if global_settings.run_checks:
            return cls.main(*args, **kwargs)
        else:
            return True


VariantResultsList = List[Tuple[bool, Variant]]


class VariantCheck(Check):
    @staticmethod
    @abstractmethod
    def check(variant: Variant) -> bool:
        """implement check logic here and return a tuple of the result and log message"""
        pass

    @classmethod
    def main(cls, variant: Variant):
        result = cls.check(variant)
        message = f"{cls.__name__}"
        message += MESSAGE_DELIMETER
        message += f"id: {variant.id}"
        if variant.filepath:
            message += MESSAGE_DELIMETER
            message += f"file: {variant.filepath}"
        message += MESSAGE_DELIMETER
        message += f"result: {result}"

        log = getattr(logger, "info") if result else getattr(logger, "error")
        log(message)

        return result


class VariantChecks:
    @staticmethod
    def run_all(variant: Variant):
        subclasses = VariantCheck.__subclasses__()
        results = [subclass.run(variant) for subclass in subclasses]
        return all(results)

    class VariantsTacticTidAgreement(VariantCheck):
        @staticmethod
        def check(variant: Variant) -> bool:
            """
            Checks that the Variant's MITRE ATT&CK Technique ID ("tid")
            is in the appropriate MITRE ATT&CK Tactic
            """
            return variant.tactic in get_valid_tactic_ids_for_tid(variant.tid)

    class VariantTidPathTidMatch(VariantCheck):
        @staticmethod
        def check(variant: Variant) -> bool:
            """
            Checks that that Variant's MITRE ATT&CK Technique ID ("tid") from its
            metadata matches the tid of its file path, if it exists.
            If no filepath is set on the Variant, this check passes.
            """
            return resolve_str_or_path(variant.filepath).parent.parent.name == variant.tid
