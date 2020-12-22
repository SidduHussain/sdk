"""TapBase abstract class."""

import abc
import json
import os

from singer.catalog import Catalog

from typing import Any, List, Optional, Type, Dict, Union
from pathlib import Path, PurePath

import click

from tap_base.plugin_base import PluginBase
from tap_base.streams.core import TapStreamBase


class TapBase(PluginBase, metaclass=abc.ABCMeta):
    """Abstract base class for taps."""

    default_stream_class: Optional[Type[TapStreamBase]] = None

    # Constructor

    def __init__(
        self,
        config: Union[PurePath, str, dict, None] = None,
        catalog: Union[PurePath, str, dict, None] = None,
        state: Union[PurePath, str, dict, None] = None,
    ) -> None:
        """Initialize the tap."""
        self._streams: Dict[str, TapStreamBase] = {}
        if isinstance(state, dict):
            state_dict = state
        else:
            state_dict = self.read_optional_json_file(state) or {}
        if isinstance(catalog, dict):
            catalog_dict = catalog
        else:
            catalog_dict = self.read_optional_json_file(catalog) or {}
        self._state = state_dict or {}
        super().__init__(config=config)
        if catalog:
            self.logger.info("loading catalog streams...")
            list_of_streams = self.load_catalog_streams(
                catalog=catalog_dict, config=self._config, state=self._state,
            )
        else:
            self.logger.info("discovering catalog streams...")
            list_of_streams = self.discover_streams()
        for stream in list_of_streams:
            self._streams[stream.name] = stream

    # Class properties

    @property
    def streams(self) -> Dict[str, TapStreamBase]:
        return self._streams

    @property
    def capabilities(self) -> List[str]:
        """Return a list of supported capabilities."""
        result = ["sync", "catalog", "state"]
        if self.discoverable:
            result.append("discover")
        return result

    # Stream type detection:

    @classmethod
    def get_stream_class(cls, stream_name: str) -> Type[TapStreamBase]:
        if not cls.default_stream_class:
            raise ValueError(
                "No stream class detected for '{cls.name}' stream '{stream_name}'"
                "and no default_stream_class defined."
            )
        return cls.default_stream_class

    def run_discovery(self) -> str:
        """Write the catalog json to STDOUT and return the same as a string."""
        catalog_json = self.get_catalog_json()
        print(catalog_json)
        return catalog_json

    def get_singer_catalog(self) -> Catalog:
        """Return a Catalog object."""
        catalog_entries = [
            stream.singer_catalog_entry for stream in self.streams.values()
        ]
        return Catalog(catalog_entries)

    def get_catalog_json(self) -> str:
        return json.dumps(self.get_singer_catalog().to_dict(), indent=2)

    # Sync methods

    def sync_one(self, stream_name: str):
        """Sync a single stream."""
        if stream_name not in self.streams:
            raise ValueError(
                f"Could not find stream '{stream_name}' in streams list: "
                f"{sorted(self.streams.keys())}"
            )
        stream = self.streams[stream_name]
        stream.sync()

    def sync_all(self):
        """Sync all streams."""
        for stream in self.streams.values():
            stream.sync()

    # Command Line Execution

    @classmethod
    def build_cli(cls):
        @click.option("--version", is_flag=True)
        @click.option("--discover", is_flag=True)
        @click.option("--config")
        @click.option("--catalog")
        @click.command()
        def cli(
            version: bool = False,
            discover: bool = False,
            config: str = None,
            state: str = None,
            catalog: str = None,
        ):
            """Handle command line execution."""
            if version:
                cls.print_version()
                return
            tap = cls(config=config, state=state, catalog=catalog)
            if discover:
                tap.run_discovery()
            else:
                tap.sync_all()

        return cli

    # Abstract stream detection methods:

    def load_catalog_streams(
        self, catalog: dict, state: dict, config: dict
    ) -> List[TapStreamBase]:
        """Return a list of streams from the provided catalog."""
        result: List[TapStreamBase] = []
        stream_entries: List[Dict] = catalog["streams"]
        for stream_entry in stream_entries:
            stream_name = stream_entry["tap_stream_id"]
            new_stream: TapStreamBase = self.get_stream_class(
                stream_name
            ).from_stream_dict(stream_dict=stream_entry, state=state, config=config)
            result.append(new_stream)
        return result

    def discover_streams(self) -> List[TapStreamBase]:
        """Return a list of discovered streams."""
        raise NotImplementedError(
            f"Tap '{self.name}' does not support discovery. "
            "Please set the '--catalog' command line argument and try again."
        )


cli = TapBase.build_cli()
