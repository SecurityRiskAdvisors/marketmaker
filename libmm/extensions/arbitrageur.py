from enum import Enum, auto

from libmm.sql import (
    session,
    LinkedData,
    LinkedDataTarget,
    LinkedDataFormat,
    Blueprint,
)
from libmm.extension import (
    AbstractUserHook,
    EventTypes,
    UserHookSetting,
    UserHookSettingT,
)
from libmm.log import logger
from libmm.type import List, Set


URL_TEMPLATE = "{darkpool_url}{arbitrageur_directory}/{blueprint_id}.ipynb"


class ArbitrageurSettings(Enum):
    DarkpoolUrl = auto()
    ArbitrageurDirectory = auto()


class ArbitrageurHook(AbstractUserHook):
    def __init__(self):
        self.enabled = False
        self.__settings = {
            ArbitrageurSettings.DarkpoolUrl: UserHookSetting(name="darkpool", parent=self),
            ArbitrageurSettings.ArbitrageurDirectory: UserHookSetting(name="directory", parent=self),
        }

        self._link_populated = False

    @property
    def name(self):
        return "arbitrageur"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: ArbitrageurSettings):
        return self.__settings.get(setting).value

    def set_value(self, setting: ArbitrageurSettings, value):
        return self.__settings.get(setting).value_callback(value)

    def populate_linked_data(self):
        if not self._link_populated:
            for blueprint in session.query(Blueprint).all():  # type: Blueprint
                url = URL_TEMPLATE.format(
                    darkpool_url=self.get_value(ArbitrageurSettings.DarkpoolUrl),
                    arbitrageur_directory=self.get_value(ArbitrageurSettings.ArbitrageurDirectory),
                    blueprint_id=blueprint.id,
                )
                friendly_name = f"{blueprint.name}.ipynb"

                button = f"""
                    <a download="{friendly_name}" class="card-footer-item" href="{url}">
                        <span class="icon-text">
                            <span class="icon">
                                <i class="fas fa-download"></i>
                            </span>
                            <span>Download notebook</span>
                        </span>
                    </a>
                """

                session.add(
                    LinkedData(
                        blueprint_id=blueprint.id,
                        target_type=LinkedDataTarget.Blueprint,
                        data_format=LinkedDataFormat.Unformatted,
                        data=button,
                        origin=self.name,
                        display_name="Jupyter Notebook",
                    )
                )

            session.commit()
            self._link_populated = True

    def hook(self, event_type, context):
        # since this is basically only for use with darkpool, dont need to hook
        # the blueprint load event since all blueprints are loaded before
        # signalling the link table ready
        if event_type == EventTypes.LinkTableReady:
            self.do_start(required_settings=self.settings)
            if self.enabled:
                self.populate_linked_data()

    def do_start(self, required_settings: List[UserHookSettingT]):
        if all([setting.value in [None, ""] for setting in required_settings]):
            self.enabled = False
            logger.warning(f'Extension "{self.name}" disabled due to missing values')
        else:
            self.enabled = True


hook = ArbitrageurHook()
