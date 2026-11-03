from __future__ import annotations

import time

from features.activation.domain.errors import JourneyError
from features.activation.domain.journey import Journey
from features.activation.infrastructure.hardware_probe import HardwareProbe
from features.activation.infrastructure.journey_store import JourneyStore
from features.activation.infrastructure.sequence_catalog import SequenceCatalog


class InitializeJourneyUseCase:
    def __init__(self, store: JourneyStore, catalog: SequenceCatalog, probe: HardwareProbe) -> None:
        self._store = store
        self._catalog = catalog
        self._probe = probe

    def execute(self, force_new: bool = False) -> Journey:
        now = time.time()
        if not force_new:
            existing = self._store.load()
            if existing is not None:
                return existing

        self._catalog.scan()
        hardware = self._probe.detect_facts()
        ordered_sequences = self._catalog.ordered()

        applicable_ids = [
            seq.id
            for seq in ordered_sequences
            if seq.applies(hardware, {})
        ]

        if not applicable_ids:
            raise JourneyError("journey.no_applicable_sequences")

        journey = Journey.new(now)
        journey.start(applicable_ids, now)
        self._store.save(journey)
        return journey
