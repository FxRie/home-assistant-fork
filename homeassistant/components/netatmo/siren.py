from enum import StrEnum, auto

from pyatmo import ApiError as NetatmoApiError, modules as NaModules

from homeassistant.components.netatmo.camera import NetatmoModuleEntity
from homeassistant.components.siren import (
    SirenEntity,
    SirenEntityDescription,
    SirenEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_CAMERA_LIGHT_MODE,
    ATTR_PERSON,
    ATTR_PERSONS,
    CAMERA_LIGHT_MODES,
    CONF_URL_SECURITY,
    DATA_CAMERAS,
    DATA_EVENTS,
    DOMAIN,
    EVENT_TYPE_OFF,
    EVENT_TYPE_ON,
    INDOOR_SIREN_TRIGGERS,
    MANUFACTURER,
    NETATMO_CREATE_SIREN,
)

from .data_handler import EVENT, HOME, SIGNAL_NAME, NetatmoDevice


class SirenStatus(StrEnum):
    """This are the states which could be returned by the siren as status."""

    NOW_NEWS = "now_news"
    NO_SOUND = "no_sound"
    WARNING = "warning"
    SOUND = "sound"
    PLAYING_RECORD_0 = "playing_record_0"
    PLAYING_RECORD_1 = "playing_record_1"
    PLAYING_RECORD_2 = "playing_record_2"
    PLAYING_RECORD_3 = "playing_record_3"
    UNKNOWN = auto()

UNKNOWN
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the Netatmo indoor smart siren."""

    @callback
    def _create_entity(netatmo_device: NetatmoDevice) -> None:
        entity = NetatmoSmartIndoorSiren(netatmo_device)
        async_add_entities([entity])

    entry.async_on_unload(
        async_dispatcher_connect(hass, NETATMO_CREATE_SIREN, _create_entity)
    )

    platform = entity_platform.async_get_current_platform()

    # platform.async_register_entity_service(
    #     SERVICE_SET_MONITORING_ON,
    #     {vol.Required(ATTR_PERSONS): vol.All(cv.ensure_list, [cv.string])},
    #     "_service_set_persons_home",
    # )
    # platform.async_register_entity_service(
    #     SERVICE_SET_MONITORING_OFF,
    #     {vol.Optional(ATTR_PERSON): cv.string},
    #     "_service_set_person_away",
    # )

    # platform.async_register_entity_service(
    #     SERVICE_SET_CAMERA_LIGHT,
    #     {vol.Required(ATTR_CAMERA_LIGHT_MODE): vol.In(CAMERA_LIGHT_MODES)},
    #     "_service_set_camera_light",
    # )


class NetatmoSmartIndoorSiren(NetatmoModuleEntity, SirenEntity):
    """Representation of a Netatmo indoor siren mostly connected to a camera"""

    _attr_has_entity_name = "test"

    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.TONES
    )
    _attr_configuration_url = CONF_URL_SECURITY
UNKNOWN
    _attr_brand = MANUFACTURER
    device: NaModules.NIS

    _monitoring: bool | None = None
    _status: SirenStatus = SirenStatus.UNKNOWN

    _attr_name = None

    def __init__(
        self,
        netatmo_device: NetatmoDevice,
    ) -> None:
        """ Initialization for access to Netatmo Siren. """

        SirenEntity.__init__(self)
        super().__init__(netatmo_device)

        self._attr_unique_id = f"{netatmo_device.device.entity_id}-{self.device_type}"

        self._publishers.extend(
            [
                {
                    "name": HOME,
                    "home_id": self.home.entity_id,
                    SIGNAL_NAME: f"{HOME}-{self.home.entity_id}",
                },
                {
                    "name": EVENT,
                    "home_id": self.home.entity_id,
                    SIGNAL_NAME: f"{EVENT}-{self.home.entity_id}",
                },
            ]
        )

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await super().async_added_to_hass()

        for event_type in INDOOR_SIREN_TRIGGERS:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    f"signal-{DOMAIN}-webhook-{event_type}",
                    self.handle_event,
                )
            )

        self.hass.data[DOMAIN][DATA_CAMERAS][self.device.entity_id] = self.device.name
