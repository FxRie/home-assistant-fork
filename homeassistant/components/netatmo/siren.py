"""This module is made for netatmo indoor advanced sirens connected to the cameras."""

from enum import IntEnum, auto
import logging
from typing import Any

from pyatmo import DeviceType as NaDeviceType, modules as NaModules
import voluptuous as vol

from homeassistant.components.siren import SirenEntity, SirenEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_URL_SECURITY,
    DATA_SIRENS,
    DOMAIN,
    EVENT_TYPE_SIREN_SOUNDING,
    EVENT_TYPE_SIREN_TAMPERED,
    MANUFACTURER,
    NETATMO_CREATE_SIREN,
    SERVICE_SET_MONITORING,
    WEBHOOK_PUSH_TYPE,
)
from .data_handler import EVENT, HOME, SIGNAL_NAME, NetatmoDevice
from .entity import NetatmoModuleEntity
from .helper import (
    BaseIntEnum,
    BaseStrEnum,
    iter_first_or_default,
    try_parse,
    try_parse_enum,
    try_pop,
)

_LOGGER = logging.getLogger(__name__)


class IndoorSirenTriggers(BaseStrEnum):
    """The mapping and typing for indoor siren event triggers."""

    Sounding = EVENT_TYPE_SIREN_SOUNDING
    Tempered = EVENT_TYPE_SIREN_TAMPERED
    Unknown = auto()


class AvailableSounds(IntEnum):
    """Mapping helper for available sounds."""

    BARKINGDOG = 0
    WHININGBABY = 1
    HOUSEHOLD = 2
    BEEPING = 3


AvailableSoundToParamMappings: dict[AvailableSounds, str] = {
    AvailableSounds.BARKINGDOG: "playing_record_0",
    AvailableSounds.WHININGBABY: "playing_record_1",
    AvailableSounds.HOUSEHOLD: "playing_record_2",
    AvailableSounds.BEEPING: "playing_record_3",
}

AvailableSoundToIdentifierMappings: dict[int, str] = {
    0: "Barking dog",
    1: "Crying baby",
    2: "Household",
    3: "Beeping",
}


class SirenStatus(BaseStrEnum):
    """This are the states which could be returned by the siren as status."""

    NOW_NEWS = "now_news"
    NO_SOUND = "no_sound"
    WARNING = "warning"
    SOUND = "sound"
    PLAYING_RECORD_0 = AvailableSoundToParamMappings[AvailableSounds(0)]
    PLAYING_RECORD_1 = AvailableSoundToParamMappings[AvailableSounds(1)]
    PLAYING_RECORD_2 = AvailableSoundToParamMappings[AvailableSounds(2)]
    PLAYING_RECORD_3 = AvailableSoundToParamMappings[AvailableSounds(3)]
    UNKNOWN = auto()


class SirenSoundingSubtype(BaseIntEnum):
    """Mappings to sounding event subtypes."""

    NOT_SOUNDING = 0
    SOUNDING = 1
    UNKNOWN = 2


class SirenTamperedSubtype(BaseIntEnum):
    """Mappings to tampered event subtypes."""

    READY = 0
    TAMPERED = 1
    UNKNOWN = 2


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

    platform.async_register_entity_service(
        SERVICE_SET_MONITORING,
        {vol.Optional("tone"): vol.In(AvailableSounds)},
        "_service_set_monitoring",
    )


class NetatmoSmartIndoorSiren(NetatmoModuleEntity, SirenEntity):
    """Representation of a Netatmo indoor siren mostly connected to a camera."""

    _attr_has_entity_name = True
    # The name has to be none as this is the main function of the indoor siren
    _attr_name = None

    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.TONES
    )
    _attr_configuration_url = CONF_URL_SECURITY

    _attr_brand = MANUFACTURER
    device: NaModules.NIS  # pyright: ignore[reportIncompatibleVariableOverride]

    _monitoring: bool | None = None
    _status: SirenStatus = SirenStatus.UNKNOWN

    def __init__(
        self,
        netatmo_device: NetatmoDevice,
    ) -> None:
        """Initialization for access to Netatmo Siren."""

        SirenEntity.__init__(self)
        super().__init__(netatmo_device)

        self._attr_unique_id = f"{netatmo_device.device.entity_id}-{self.device_type}"

        self._attr_bridge_id: str | None = self.device.bridge
        self._attr_is_tempered: bool | None = None
        self._attr_tempered_message: str | None = None
        self._attr_status: SirenStatus | None = None
        self._attr_available_tones = AvailableSoundToIdentifierMappings

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

    @callback
    def async_update_callback(self) -> None:
        """Update the entity's state."""
        self._attr_is_on = self.device.monitoring is True
        self._attr_available = self.device.reachable is True

        self._attr_extra_state_attributes.update(
            {
                "id": self.device.entity_id,
                "monitoring": self.device.monitoring,
                "battery_state": self.device.battery_state,
                "bridge_id": self.device.bridge,
                "status": SirenStatus.try_get_enum_by_val(
                    self.device.status, SirenStatus.UNKNOWN
                ),
            }
        )

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        await super().async_added_to_hass()

        for event_type in IndoorSirenTriggers:
            if event_type is IndoorSirenTriggers.Unknown:
                continue

            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    f"signal-{DOMAIN}-webhook-{event_type}",
                    self.handle_event,
                )
            )

        self.hass.data[DOMAIN][DATA_SIRENS][self.device.entity_id] = self.device.name

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        json_monitoring_state = {
            "modules": [
                {
                    "id": self.device.entity_id,
                    "bridge": self._attr_bridge_id,
                    "monitoring": "on",
                },
            ],
        }

        selectedToneIdentifier: AvailableSounds | None = kwargs.get("tone")
        selectedStatusResult: str | None = (
            AvailableSoundToParamMappings.get(selectedToneIdentifier)
            if selectedToneIdentifier is not None
            else None
        )

        module_setter_item = iter_first_or_default(json_monitoring_state["modules"])
        if selectedStatusResult is not None and module_setter_item is not None:
            module_setter_item["status"] = selectedStatusResult

        await self.home.async_set_state(json_monitoring_state)
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        json_monitoring_state = {
            "modules": [
                {
                    "id": self.device.entity_id,
                    "bridge": self._attr_bridge_id,
                    "monitoring": "off",
                },
            ],
        }
        await self.home.async_set_state(json_monitoring_state)
        self._attr_is_on = False

    @callback
    def handle_event(self, event: dict) -> None:
        """Handle the eventhook events."""
        _LOGGER.error("++++++++++++++++++++event: %s", event)
        data: dict[str, str | int] = event["data"]
        eventPushType: str | int | None = data.get(WEBHOOK_PUSH_TYPE)
        if (
            data.get("device_id ") != self.device.entity_id
            or data.get("home_id") != self.home.entity_id
            or not isinstance(eventPushType, str)
        ):
            return

        eventParts: list[str] = eventPushType.split(sep="_", maxsplit=1)
        if len(eventParts) != 2:
            _LOGGER.error("Invalid event identifier received '%s'", eventPushType)
            return

        resultSirenTrigger = IndoorSirenTriggers.try_get_enum_by_val(
            try_pop(eventParts), IndoorSirenTriggers.Unknown
        )
        resultEventDeviceType = try_parse_enum(NaDeviceType, try_pop(eventParts))

        match [resultEventDeviceType, resultSirenTrigger]:
            case [NaDeviceType.NIS, IndoorSirenTriggers.Sounding]:
                match SirenSoundingSubtype.match_value(
                    data.get("sub_type"), SirenSoundingSubtype.UNKNOWN
                ):
                    case SirenSoundingSubtype.NOT_SOUNDING:
                        _LOGGER.info("Siren sounding event with not sounding received")
                        self._attr_is_on = False

                    case SirenSoundingSubtype.SOUNDING:
                        self._attr_is_on = False
                        _LOGGER.info("Siren sounding event with sounding received")

                    case SirenSoundingSubtype.UNKNOWN:
                        _LOGGER.error("Unknown siren sounding event subtype received")
                        raise ValueError(
                            f"Unrecognized event subtype: {SirenSoundingSubtype.UNKNOWN} for event siren_sounding."
                        )

            case [NaDeviceType.NIS, IndoorSirenTriggers.Tempered]:
                match SirenTamperedSubtype.match_value(
                    data.get("sub_type"), SirenTamperedSubtype.UNKNOWN
                ):
                    case SirenTamperedSubtype.READY:
                        _LOGGER.info("Siren sounding event with not sounding received")
                        self._attr_is_tempered = False
                        self._attr_tempered_message = None
                    case SirenTamperedSubtype.TAMPERED:
                        _LOGGER.info("Siren sounding event with sounding received")
                        self._attr_is_tempered = True
                        self._attr_tempered_message = try_parse(
                            str, data.get("message")
                        )
                    case SirenTamperedSubtype.UNKNOWN:
                        _LOGGER.error("Unknown siren sounding event subtype received")
                        raise ValueError(
                            f"Unrecognized event subtype: {SirenTamperedSubtype.UNKNOWN} for event siren_tampered"
                        )
                self.__update_tempered_internal(
                    self._attr_is_tempered, self._attr_tempered_message
                )
            case _:
                raise ValueError(
                    f"Unrecognized event or could not be parsed: {eventPushType}"
                )

        self.async_write_ha_state()

    def __update_tempered_internal(
        self, isTampered: bool, tamperedMessage: str | None
    ) -> None:
        self._attr_extra_state_attributes.update(
            {
                "is_tampered": self._attr_is_tempered,
                "tempered_message": self._attr_tempered_message,
            },
        )
